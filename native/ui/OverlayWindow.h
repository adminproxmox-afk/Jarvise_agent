#pragma once

#include <chrono>
#include <functional>
#include <string>

#include <windows.h>
#include <objidl.h>
#include <gdiplus.h>

#include "system/TrayIcon.h"

namespace jarvis::ui {

class OverlayWindow {
public:
    explicit OverlayWindow(HINSTANCE instance);
    ~OverlayWindow();

    bool Create(const std::wstring& title);
    HWND Handle() const { return hwnd_; }

    void InstallTrayIcon(const std::wstring& tooltip);
    void RemoveTrayIcon();
    void ShowStartup(int durationMs);

    void SetActivationCallback(std::function<void()> callback) { onActivate_ = std::move(callback); }
    void SetReloadCallback(std::function<void()> callback) { onReload_ = std::move(callback); }
    void SetExitCallback(std::function<void()> callback) { onExit_ = std::move(callback); }

private:
    static LRESULT CALLBACK StaticWndProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam);
    LRESULT WndProc(UINT message, WPARAM wParam, LPARAM lParam);

    void Paint();
    void DrawScene(Gdiplus::Graphics& graphics, const RECT& rect);
    void ShowTrayMenu();
    void RegisterClass();

    HINSTANCE instance_{};
    HWND hwnd_{nullptr};
    ULONG_PTR gdiplusToken_{};
    jarvis::system::TrayIcon tray_;
    std::function<void()> onActivate_;
    std::function<void()> onReload_;
    std::function<void()> onExit_;
    std::chrono::steady_clock::time_point shownAt_{};
    int durationMs_{5200};
    bool visible_{false};
};

}  // namespace jarvis::ui
