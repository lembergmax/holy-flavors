Option Explicit

Dim fileSystem, projectDirectory, shell, command
Set fileSystem = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

projectDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = projectDirectory
command = "pyw -3 """ & projectDirectory & "\Holy-Flavors.pyw"""
shell.Run command, 0, False
