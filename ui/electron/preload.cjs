const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisDesktop", {
  platform: () => ipcRenderer.invoke("jarvis:platform")
});
