# OpenSim GUI/Jython bridge. Avoid newer Python grammar in the GUI parser.
# All native GUI operations run on Swing's event thread, not an RPC thread.
from __future__ import with_statement
import hashlib
import math
import os
import time
import traceback
from java.awt.event import ActionListener
from javax.swing import Timer
from org.opensim.console import gui
from org.opensim.view.pub import ViewDB
from org.json.simple import JSONValue
from org.json.simple.parser import JSONParser
from java.util import Map, List
from java.util import UUID
from java.lang import Number, Boolean, String, Double, Float
from java.lang.management import ManagementFactory
from org.opensim.modeling import opensimCommon
from org.opensim.utils import TheApp


def _bridge_decode(value):
    if value is None:
        return None
    if isinstance(value, Map):
        return dict((unicode(e.getKey()), _bridge_decode(e.getValue())) for e in value.entrySet())
    if isinstance(value, List):
        return [_bridge_decode(v) for v in value]
    if isinstance(value, Boolean):
        return value.booleanValue()
    if isinstance(value, (Double, Float)):
        return float(value)
    if isinstance(value, Number):
        return int(value)
    if isinstance(value, String):
        return unicode(value)
    return value


class _BridgeJson(object):
    # OpenSim 4.3 ships Jython 2.5.2, which has no stdlib json module.
    def loads(self, text):
        return _bridge_decode(JSONParser().parse(text))

    def dumps(self, value, ensure_ascii=True, sort_keys=False):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, basestring):
            return u'"' + unicode(JSONValue.escape(value)) + u'"'
        if isinstance(value, (int, long, float)):
            return str(value)
        if isinstance(value, dict):
            keys = sorted(value) if sort_keys else value.keys()
            return u"{" + u",".join(self.dumps(unicode(k)) + u":" + self.dumps(value[k], sort_keys=sort_keys) for k in keys) + u"}"
        if isinstance(value, (list, tuple)):
            return u"[" + u",".join(self.dumps(v, sort_keys=sort_keys) for v in value) + u"]"
        raise TypeError("Unsupported GUI JSON value: " + str(type(value)))


json = _BridgeJson()


def _bridge_read(path):
    with open(path, "rb") as stream:
        data = stream.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise ValueError("GUI message exceeds 1 MiB")
    return json.loads(data.decode("utf-8"))


def _bridge_write(path, value):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        try:
            os.makedirs(parent)
        except OSError:
            if not os.path.isdir(parent):
                raise
    temporary = path + ".writing"
    with open(temporary, "wb") as stream:
        stream.write(json.dumps(value, ensure_ascii=True).encode("utf-8"))
    # Each response has a unique name. Heartbeat replacement uses Java NIO.
    from java.nio.file import Files, Paths, StandardCopyOption
    Files.move(Paths.get(temporary), Paths.get(path), StandardCopyOption.REPLACE_EXISTING)


_bridge_config = _bridge_read(bridge_config_path)
_bridge_folder = os.path.dirname(os.path.abspath(bridge_config_path))
_bridge_undo = []


def _bridge_under(path, root):
    path = os.path.normcase(os.path.realpath(path))
    root = os.path.normcase(os.path.realpath(root))
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _bridge_input(path, extension):
    if not os.path.isabs(path) or not path.lower().endswith(extension) or not os.path.isfile(path):
        raise ValueError("Expected an existing absolute local " + extension + " path")
    if not any(_bridge_under(path, root) for root in _bridge_config["allowed_roots"] + [_bridge_config["results_root"]]):
        raise ValueError("GUI input is outside configured roots")
    return path


def _bridge_model():
    model = gui.getCurrentModel()
    if model is None:
        raise ValueError("No current model in OpenSim GUI")
    return model


def _bridge_pose(model, coordinates):
    state = gui.getStateRef(model)
    for name, value in coordinates.items():
        value = float(value)
        if value != value or abs(value) == float("inf"):
            raise ValueError("Coordinate values must be finite")
        model.getCoordinateSet().get(name).setValue(state, value)
    model.realizePosition(state)
    # gui.setCoordinateValue schedules reportTimeChange(0), which can reapply a
    # loaded motion and overwrite this pose. We already run on the Swing EDT.
    ViewDB.getInstance().updateModelDisplay(model)


def _bridge_status():
    global _bridge_revision, _bridge_last_fingerprint
    model = gui.getCurrentModel()
    result = {"connected": True, "bridge_id": _bridge_config["bridge_id"], "model_loaded": model is not None,
              "bridge_version": "1.1.0", "protocol_version": 1, "capabilities": ["selection", "snapshot_png", "undo_pose", "select_component", "queue_identity_recovery", "configuration_reload", "atomic_state_guard"],
              "thread": "Swing event dispatch thread", "opensim_version": str(opensimCommon.GetVersionAndDate()),
              "gui_process": str(ManagementFactory.getRuntimeMXBean().getName())}
    result["resources_dir"] = unicode(TheApp.getResourcesDir() or "")
    result["gui_user_dir"] = unicode(TheApp.getUserDir())
    if model is not None:
        state = gui.getStateRef(model)
        coords = model.getCoordinateSet()
        values = dict((str(coords.get(i).getName()), coords.get(i).getValue(state)) for i in range(coords.getSize()))
        # Snapshot signature covers both model definition and current pose.
        signature = hashlib.sha256((str(model.dump()) + json.dumps(values, sort_keys=True)).encode("utf-8")).hexdigest()
        result.update(name=str(model.getName()), signature=signature, coordinate_values=values,
                      counts={"bodies": model.getBodySet().getSize(), "joints": model.getJointSet().getSize(),
                              "coordinates": coords.getSize(), "muscles": model.getMuscles().getSize()})
        result['time_s'] = state.getTime()
    fingerprint = json.dumps([result.get('signature'), result.get('time_s'), result['model_loaded']], sort_keys=True)
    if fingerprint != _bridge_last_fingerprint:
        _bridge_revision += 1
        _bridge_last_fingerprint = fingerprint
    result['state_token'] = _bridge_instance_id + ':' + str(_bridge_revision)
    result['gui_revision'] = _bridge_revision
    return result


def _bridge_dispatch(op, args):
    global _bridge_revision
    writes = ('open_model', 'load_motion', 'set_coordinate', 'undo_pose', 'select_component', 'reload_configuration', 'stop')
    if op in writes:
        current = _bridge_status()
        if args.get('_expected_state_token') != current['state_token']:
            raise ValueError('GUI_CONFLICT: GUI model, pose, time or revision changed; refresh current GUI status and review before editing')
    result = _bridge_operation(op, args)
    if op in writes:
        _bridge_revision += 1
        current = _bridge_status()
        if isinstance(result, dict):
            result['state_token'] = current['state_token']
            result['gui_revision'] = current['gui_revision']
            if 'gui' in result:result['gui'] = current
    return result


def _bridge_operation(op, args):
    global _bridge_config
    if op == "reload_configuration":
        configuration = args["configuration"]
        if configuration.get("bridge_id") != _bridge_config["bridge_id"] or configuration.get("token") != _bridge_config["token"]:
            raise ValueError("Bridge identity must remain unchanged")
        if not isinstance(configuration.get("allowed_roots"), list) or not configuration.get("results_root"):
            raise ValueError("Invalid bridge configuration")
        _bridge_write(bridge_config_path, configuration)
        _bridge_config = configuration
        return {"reconfigured": True, "gui": _bridge_status()}
    if op == "selection":
        from org.opensim.view import ExplorerTopComponent
        nodes = ExplorerTopComponent.getDefault().getExplorerManager().getSelectedNodes()
        selected = []
        for node in list(nodes)[:100]:
            entry = {"name": unicode(node.getDisplayName()), "node_class": unicode(type(node).__name__)}
            if hasattr(node, "getOpenSimObject"):
                obj = node.getOpenSimObject()
                entry["object_name"] = unicode(obj.getName())
                entry["object_class"] = unicode(obj.getConcreteClassName())
                if hasattr(obj, "getAbsolutePathString"):
                    entry["component_path"] = unicode(obj.getAbsolutePathString())
            selected.append(entry)
        return {"selection": selected, "source": "OpenSim Navigator ExplorerManager", "gui": _bridge_status()}
    if op == "select_component":
        from org.opensim.view import ExplorerTopComponent
        obj = _bridge_model().getComponent(args["component_path"])
        ExplorerTopComponent.getDefault().selectNodeForObject(obj)
        return _bridge_dispatch("selection", {})
    if op == "snapshot_png":
        from org.openide.windows import WindowManager
        from java.awt.image import BufferedImage
        from javax.imageio import ImageIO
        from java.io import File
        destination = args["destination"]
        if not _bridge_under(destination, _bridge_config["results_root"]) or os.path.exists(destination):
            raise ValueError("Image must use a fresh result path")
        frame = WindowManager.getDefault().getMainWindow()
        width, height = frame.getWidth(), frame.getHeight()
        if width <= 0 or height <= 0 or width * height > 16000000:
            raise ValueError("GUI window dimensions exceed capture limits")
        image = BufferedImage(width, height, BufferedImage.TYPE_INT_RGB)
        graphics = image.createGraphics()
        try:
            frame.printAll(graphics)
        finally:
            graphics.dispose()
        if not ImageIO.write(image, "png", File(destination)):
            raise ValueError("PNG encoding failed")
        return {"image_file": destination, "width": width, "height": height,
                "method": "Swing window printAll; excludes other desktop apps",
                "limitation": "Hardware-accelerated embedded 3D/browser surfaces may be blank; use render_model for native pose geometry."}
    if op == "undo_pose":
        if not _bridge_undo:
            raise ValueError("No bridge pose edit to undo")
        item = _bridge_undo[-1]
        if item.get('client_id') != args.get('_client_id'):
            raise ValueError('GUI_OWNER_CONFLICT: latest pose edit belongs to another MCP session')
        current = _bridge_status()
        if current.get("signature") != item["after_signature"]:
            raise ValueError("GUI model/pose changed after the edit; refusing stale undo")
        _bridge_pose(_bridge_model(), item["coordinate_values"])
        _bridge_undo.pop()
        result = _bridge_status()
        if _bridge_undo:
            _bridge_undo[-1]["after_signature"] = result["signature"]
        return result
    if op == "status":
        return _bridge_status()
    if op == "open_model":
        if args.get("expected_signature") and _bridge_status().get("signature") != args["expected_signature"]:
            raise ValueError("GUI current model/pose changed since the expected snapshot")
        gui.loadModel(_bridge_input(args["path"], ".osim"))
        del _bridge_undo[:]
        model = _bridge_model()
        if args.get("coordinates"):
            _bridge_pose(model, args["coordinates"])
        return _bridge_status()
    if op == "load_motion":
        _bridge_model()
        gui.loadMotion(_bridge_input(args["path"], ".mot"))
        result = _bridge_status()
        result["motion_file"] = args["path"]
        return result
    if op == "set_coordinate":
        model = _bridge_model()
        if args.get("expected_signature") and _bridge_status()["signature"] != args["expected_signature"]:
            raise ValueError("GUI model/pose changed since the expected snapshot")
        value = float(args["value"])
        if value != value or abs(value) == float("inf"):
            raise ValueError("Coordinate value must be finite")
        before = _bridge_status()
        _bridge_pose(model, {args["name"]: value})
        after = _bridge_status()
        _bridge_undo.append({"coordinate_values": before["coordinate_values"], "after_signature": after["signature"], "client_id": args.get('_client_id')})
        del _bridge_undo[:-20]
        return after
    if op == "snapshot":
        destination = args["destination"]
        if not _bridge_under(destination, _bridge_config["results_root"]) or os.path.exists(destination):
            raise ValueError("GUI snapshots must use a fresh file under results_root")
        model = _bridge_model()
        if hasattr(model, "printToXML"):
            model.printToXML(destination)
        else:
            getattr(model, "print")(destination)
        result = _bridge_status()
        result["model_file"] = destination
        return result
    if op == "stop":
        _opensim_mcp_timer.stop()
        try:
            os.remove(os.path.join(_bridge_folder, "heartbeat.json"))
        except OSError:
            pass
        return {"connected": False, "stopped": True}
    raise ValueError("Unsupported GUI operation")


class _OpenSimMcpListener(ActionListener):
    def __init__(self):
        self.last_heartbeat = 0

    def actionPerformed(self, event):
        now = time.time()
        if now - self.last_heartbeat > 1:
            _bridge_write(os.path.join(_bridge_folder, "heartbeat.json"),
                          {"bridge_id": _bridge_config["bridge_id"], "time": now, "gui_process": unicode(ManagementFactory.getRuntimeMXBean().getName())})
            self.last_heartbeat = now
        for filename in sorted(os.listdir(_bridge_folder)):
            if not filename.endswith(".request.json"):
                continue
            path = os.path.join(_bridge_folder, filename)
            identifier = filename[:-len(".request.json")]
            if len(identifier) != 32 or any(c not in "0123456789abcdef" for c in identifier):
                continue
            try:
                request = _bridge_read(path)
                os.remove(path)
                if request.get("token") != _bridge_config["token"] or request.get("id") != identifier:
                    raise ValueError("GUI bridge authentication failed")
                value = _bridge_dispatch(request["operation"], request.get("arguments", {}))
                response = {"id": identifier, "ok": True, "value": value}
            except BaseException:
                response = {"id": identifier, "ok": False, "error": traceback.format_exc()[-8000:]}
            _bridge_write(os.path.join(_bridge_folder, identifier + ".response.json"), response)
            break


try:
    _opensim_mcp_timer.stop()
except NameError:
    pass
_bridge_instance_id = unicode(UUID.randomUUID().toString())
_bridge_revision = 0
_bridge_last_fingerprint = None
_opensim_mcp_timer = Timer(200, _OpenSimMcpListener())
_opensim_mcp_timer.start()
print("OpenSim MCP GUI bridge started. Requests are restricted to this local configuration.")
