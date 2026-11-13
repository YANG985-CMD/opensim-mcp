"""Read-only native API discovery; also used by the CPython 3.8 worker."""
import inspect
import re


def documentation(osim,symbol='',query='',limit=50):
    if type(limit) is not int or not 1<=limit<=100:raise ValueError('limit must be 1..100.')
    if not isinstance(symbol,str) or len(symbol)>300 or not isinstance(query,str) or len(query)>200:raise ValueError('Symbol/query length limits exceeded.')
    if not symbol:
        names=sorted(n for n in dir(osim) if not n.startswith('_') and query.lower() in n.lower())
        return {'symbols':names[:limit],'total':len(names),'opensim_version':osim.GetVersionAndDate()}
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*){0,2}',symbol):
        raise ValueError('Use a public OpenSim class/function or Class.method name.')
    value=osim
    for part in symbol.split('.'):
        value=getattr(value,part)
    doc=inspect.getdoc(value) or ''
    try:signature=str(inspect.signature(value))
    except (ValueError,TypeError):signature=None
    return {'symbol':symbol,'doc':doc[:20000],'binding_doc_available':bool(doc),'signature':signature,
            'source_reference':'https://github.com/opensim-org/opensim-core',
            'documentation_note':'Some SWIG methods omit binding docstrings; member existence is checked against this runtime. Refer to the matching upstream class/header for missing documentation.',
            'members':[n for n in dir(value) if not n.startswith('_') and query.lower() in n.lower()][:limit],
            'opensim_version':osim.GetVersionAndDate()}


def components(model,query='',class_name='',offset=0,limit=50):
    if model is None:raise ValueError('Load a model first.')
    if not isinstance(query,str) or len(query)>200 or not isinstance(class_name,str) or len(class_name)>200:raise ValueError('Component filter limits exceeded.')
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('offset must be nonnegative and limit 1..100.')
    found=[];count=0
    for component in model.getComponentsList():
        name=component.getAbsolutePathString();kind=component.getConcreteClassName()
        if query.lower() not in (name+' '+kind).lower() or (class_name and kind!=class_name):continue
        if offset<=count<offset+limit:found.append({'path':name,'name':component.getName(),'class':kind})
        count+=1
        if count>20000:raise ValueError('Component traversal limit exceeded.')
    return {'components':found,'offset':offset,'total':count,'next_offset':offset+len(found) if offset+len(found)<count else None}


def component_details(model,path):
    if model is None:raise ValueError('Load a model first.')
    if not isinstance(path,str) or not path.startswith('/') or len(path)>1000:raise ValueError('Use an absolute model component path.')
    obj=model.getComponent(path)
    props=[]
    for i in range(min(100,obj.getNumProperties())):
        prop=obj.getPropertyByIndex(i)
        props.append({'name':prop.getName(),'type':prop.getTypeName(),'value':prop.toString()[:1000]})
    sockets=[]
    names=obj.getSocketNames()
    for name in names:
        socket=obj.getSocket(name)
        sockets.append({'name':str(name),'connectee_type':socket.getConnecteeTypeName(),
                        'connectee_path':socket.getConnecteePath()})
    return {'path':obj.getAbsolutePathString(),'class':obj.getConcreteClassName(),
            'properties':props,'sockets':sockets,'property_count':obj.getNumProperties()}
