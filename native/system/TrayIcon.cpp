#include "system/TrayIcon.h"

#include "system/Logger.h"

namespace jarvis::system {

namespace {
constexpr UINT kTrayId = 41;
constexpr UINT kCommandLaunch = 41001;
constexpr UINT kCommandShow = 41002;
constexpr UINT kCommandReload = 41003;
constexpr UINT kCommandExit = 41004;
}

bool TrayIcon::Install(HWND owner, const std::wstring& tooltip) {
    data_ = {};
    data_.cbSize = sizeof(data_);
    data_.hWnd = owner;
    data_.uID = kTrayId;
    data_.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
    data_.uCallbackMessage = Message;
    data_.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    wcsncpy_s(data_.szTip, tooltip.c_str(), _TRUNCATE);

    installed_ = Shell_NotifyIconW(NIM_ADD, &data_) == TRUE;
    if (installed_) {
        data_.uVersion = NOTIFYICON_VERSION_4;
        Shell_NotifyIconW(NIM_SETVERSION, &data_);
    } else {
        Logger::Error(L"Failed to install tray icon.");
    }
    return installed_;
}

void TrayIcon::Remove() {
    if (!installed_) {
        return;
    }
    Shell_NotifyIconW(NIM_DELETE, &data_);
    installed_ = false;
}

void TrayIcon::ShowMenu(HWND owner, POINT point) const {
    HMENU menu = CreatePopupMenu();
    AppendMenuW(menu, MF_STRING, kCommandLaunch, L"Launch workspace");
    AppendMenuW(menu, MF_STRING, kCommandShow, L"Show JARVIS overlay");
    AppendMenuW(menu, MF_STRING, kCommandReload, L"Reload config");
    AppendMenuW(menu, MF_SEPARATOR, 0, nullptr);
    AppendMenuW(menu, MF_STRING, kCommandExit, L"Exit");

    SetForegroundWindow(owner);
    TrackPopupMenu(menu, TPM_RIGHTBUTTON, point.x, point.y, 0, owner, nullptr);
    DestroyMenu(menu);
    PostMessageW(owner, WM_NULL, 0, 0);
}

}  // namespace jarvis::system
