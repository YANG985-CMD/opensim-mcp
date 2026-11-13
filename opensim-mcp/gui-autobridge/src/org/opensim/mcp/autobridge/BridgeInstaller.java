package org.opensim.mcp.autobridge;

import java.io.File;
import java.io.FileInputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import java.util.logging.Level;
import java.util.logging.Logger;
import javax.swing.Timer;
import org.openide.modules.InstalledFileLocator;
import org.openide.windows.WindowManager;
import org.opensim.console.ScriptingShellTopComponent;

/** One startup hook; the authenticated RPC implementation remains in Python. */
public final class BridgeInstaller extends org.openide.modules.ModuleInstall {
    private static final Logger LOG = Logger.getLogger(BridgeInstaller.class.getName());
    private transient Timer retry;

    @Override
    public void restored() {
        WindowManager.getDefault().invokeWhenUIReady(new Runnable() {
            @Override public void run() {
                // The server may start after the GUI or recreate its temporary
                // bootstrap later. Wait until it is present, then run once.
                retry = new Timer(2000, event -> startIfReady());
                retry.setInitialDelay(2500);
                retry.start();
                LOG.info("OpenSim MCP startup hook registered");
            }
        });
    }

    private void startIfReady() {
        try {
            String configured = System.getProperty("opensim.mcp.gui.bootstrap");
            if (configured == null) configured = System.getenv("OPENSIM_MCP_GUI_BOOTSTRAP");
            if (configured == null) {
                File config = InstalledFileLocator.getDefault().locate(
                        "modules/org-opensim-mcp-autobridge.properties",
                        "org.opensim.mcp.autobridge", false);
                if (config == null || !config.isFile()) return;
                Properties properties = new Properties();
                try (InputStreamReader stream = new InputStreamReader(
                        new FileInputStream(config), StandardCharsets.UTF_8)) {
                    properties.load(stream);
                }
                configured = properties.getProperty("bootstrap");
            }
            if (configured == null || configured.trim().isEmpty()) return;
            File script = new File(configured);
            if (!script.isAbsolute() || configured.startsWith("\\\\")) {
                throw new IllegalArgumentException("Bootstrap must be an absolute local file");
            }
            if (!script.isFile()) return;
            retry.stop();
            // Timer events and all native GUI calls run on Swing's EDT.
            ScriptingShellTopComponent.getDefault().getConsole()
                    .executeFile(script.getCanonicalPath());
            LOG.info("OpenSim MCP bootstrap dispatched: " + script.getCanonicalPath());
        } catch (Exception error) {
            if (retry != null) retry.stop();
            LOG.log(Level.SEVERE, "OpenSim MCP automatic startup failed; use manual bootstrap", error);
        }
    }

    @Override
    public void close() {
        if (retry != null) retry.stop();
    }
}
