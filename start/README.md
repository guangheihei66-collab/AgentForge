# Legacy AgentForge startup wrappers

The canonical Windows entry points are the root-level [`Start-AgentForge.bat`](../Start-AgentForge.bat) and [`Stop-AgentForge.bat`](../Stop-AgentForge.bat). They delegate to the maintained `launcher/` implementation.

The files in this directory are retained as legacy compatibility wrappers only. They are not the documented release-candidate entry point.

Runtime logs and PID files stay under `D:\AgentProjectData\AgentForge\runtime\`, outside the source repository.
