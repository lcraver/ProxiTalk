' getclipboard.vbs
Option Explicit

Dim objFSO, objHTML, strClip, tempFile

Set objFSO = CreateObject("Scripting.FileSystemObject")
Set objHTML = CreateObject("htmlfile")

' Define the path for the temporary file
tempFile = "clipboard_temp.txt"

' Use error handling in case clipboard does not contain text
On Error Resume Next
strClip = objHTML.ParentWindow.ClipboardData.GetData("text")
On Error GoTo 0 ' Turn off error handling

' Write the clipboard contents to a temporary file if it's non-empty plain text
If TypeName(strClip) = "String" And strClip <> "" Then
    ' Create the temporary file and write the clipboard data to it
    With objFSO.CreateTextFile(tempFile, True)
        .WriteLine strClip
        .Close
    End With
End If