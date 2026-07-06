#pragma once

#include <string>

#include <windows.h>
#include <shellapi.h>

namespace jarvis::system {

class TrayIcon {
public:
    static constexpr UINT Message = WM_APP + 501;

    bool Install(HWND owner, const std::wstring& tooltip);
    void Remove();
    void ShowMenu(HWND owner, POINT point) const;

private:
    NOTIFYICONDATAW data_{};
    bool installed_{false};
};

}  // namespace jarvis::system
