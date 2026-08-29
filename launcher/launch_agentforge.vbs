Option Explicit

Dim fso, shell, root, pythonw, launcher, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = fso.GetParentFolderName(fso.GetParentFolderName(WScript.ScriptFullName))
pythonw = ResolvePythonW(root)
If pythonw = "" Then
  WriteFailure root, "No approved pythonw.exe was found for this AgentForge installation."
  WScript.Quit 1
End If
launcher = fso.BuildPath(root, "launcher\agentforge_launcher.pyw")
If Not fso.FileExists(launcher) Then
  WriteFailure root, "Launcher entry point is missing."
  WScript.Quit 1
End If
command = Quote(pythonw) & " " & Quote(launcher) & " --root " & Quote(root)
shell.Run command, 0, False
WScript.Quit 0

Function ResolvePythonW(ByVal installRoot)
  Dim override, candidateRoot, i, candidate, parent, overrideW, baseW
  override = shell.Environment("Process")("AGENTFORGE_PYTHON")
  If Len(Trim(override)) > 0 Then
    If fso.FileExists(override) Then
      baseW = ResolveBasePythonW(override)
      If baseW <> "" Then
        ResolvePythonW = baseW
        Exit Function
      End If
      If LCase(fso.GetFileName(override)) = "pythonw.exe" Then
        ResolvePythonW = override
        Exit Function
      End If
      overrideW = fso.BuildPath(fso.GetParentFolderName(override), "pythonw.exe")
      If fso.FileExists(overrideW) Then
        ResolvePythonW = overrideW
        Exit Function
      End If
    End If
    ResolvePythonW = ""
    Exit Function
  End If

  candidateRoot = installRoot
  For i = 0 To 4
    candidate = fso.BuildPath(candidateRoot, "backend\.venv\Scripts\python.exe")
    baseW = ResolveBasePythonW(candidate)
    If baseW <> "" Then
      ResolvePythonW = baseW
      Exit Function
    End If
    candidate = fso.BuildPath(candidateRoot, "backend\.venv\Scripts\pythonw.exe")
    If fso.FileExists(candidate) Then
      ResolvePythonW = candidate
      Exit Function
    End If
    parent = fso.GetParentFolderName(candidateRoot)
    If Len(parent) = 0 Or LCase(parent) = LCase(candidateRoot) Then Exit For
    candidateRoot = parent
  Next
  ResolvePythonW = ""
End Function

Function ResolveBasePythonW(ByVal pythonExe)
  Dim scriptsRoot, venvRoot, configPath, stream, line, separator, home, candidate
  ResolveBasePythonW = ""
  If Not fso.FileExists(pythonExe) Then Exit Function
  scriptsRoot = fso.GetParentFolderName(pythonExe)
  venvRoot = fso.GetParentFolderName(scriptsRoot)
  configPath = fso.BuildPath(venvRoot, "pyvenv.cfg")
  If Not fso.FileExists(configPath) Then Exit Function
  On Error Resume Next
  Set stream = fso.OpenTextFile(configPath, 1, False, 0)
  Do While Not stream.AtEndOfStream
    line = Trim(stream.ReadLine)
    separator = InStr(1, line, "=", vbTextCompare)
    If separator > 0 Then
      If LCase(Trim(Left(line, separator - 1))) = "home" Then
        home = Trim(Mid(line, separator + 1))
        candidate = fso.BuildPath(home, "pythonw.exe")
        If fso.FileExists(candidate) Then
          ResolveBasePythonW = candidate
          Exit Do
        End If
      End If
    End If
  Loop
  stream.Close
  On Error GoTo 0
End Function

Function Quote(ByVal value)
  Quote = Chr(34) & value & Chr(34)
End Function

Sub WriteFailure(ByVal installRoot, ByVal message)
  Dim dataRoot, logDir, logPath, stream
  dataRoot = shell.Environment("Process")("AGENTFORGE_DATA_ROOT")
  If Len(Trim(dataRoot)) = 0 Then dataRoot = "D:\AgentProjectData\AgentForge"
  logDir = fso.BuildPath(dataRoot, "runtime\logs")
  On Error Resume Next
  If Not fso.FolderExists(logDir) Then fso.CreateFolder(logDir)
  logPath = fso.BuildPath(logDir, "launcher.log")
  Set stream = fso.OpenTextFile(logPath, 8, True, -1)
  stream.WriteLine "[" & Now & "] ERROR: " & message
  stream.Close
  On Error GoTo 0
End Sub
