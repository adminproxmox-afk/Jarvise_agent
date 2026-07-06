#include "ui/OverlayWindow.h"

#include <algorithm>
#include <cmath>

#include <dwmapi.h>
#include <windowsx.h>

#include "system/Logger.h"

namespace jarvis::ui {

namespace {

constexpr const wchar_t* kClassName = L"JARVIS.Native.Overlay";
constexpr UINT_PTR kAnimationTimer = 77;
constexpr UINT kCommandLaunch = 41001;
constexpr UINT kCommandShow = 41002;
constexpr UINT kCommandReload = 41003;
constexpr UINT kCommandExit = 41004;

float Progress(std::chrono::steady_clock::time_point started, int durationMs) {
    if (durationMs <= 0) {
        return 1.0f;
    }
    const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
                             std::chrono::steady_clock::now() - started)
                             .count();
    return std::clamp(static_cast<float>(elapsed) / static_cast<float>(durationMs), 0.0f, 1.0f);
}

Gdiplus::Color ColorArgb(BYTE a, BYTE r, BYTE g, BYTE b) {
    return Gdiplus::Color(a, r, g, b);
}

}  // namespace

OverlayWindow::OverlayWindow(HINSTANCE instance) : instance_(instance) {
    Gdiplus::GdiplusStartupInput input;
    Gdiplus::GdiplusStartup(&gdiplusToken_, &input, nullptr);
}

OverlayWindow::~OverlayWindow() {
    RemoveTrayIcon();
    if (hwnd_) {
        DestroyWindow(hwnd_);
    }
    if (gdiplusToken_ != 0) {
        Gdiplus::GdiplusShutdown(gdiplusToken_);
    }
}

bool OverlayWindow::Create(const std::wstring& title) {
    RegisterClass();

    const int width = GetSystemMetrics(SM_CXSCREEN);
    const int height = GetSystemMetrics(SM_CYSCREEN);
    hwnd_ = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
        kClassName,
        title.c_str(),
        WS_POPUP,
        0,
        0,
        width,
        height,
        nullptr,
        nullptr,
        instance_,
        this);

    if (!hwnd_) {
        return false;
    }

    SetLayeredWindowAttributes(hwnd_, 0, 232, LWA_ALPHA);
    MARGINS margins{-1};
    DwmExtendFrameIntoClientArea(hwnd_, &margins);
    return true;
}

void OverlayWindow::InstallTrayIcon(const std::wstring& tooltip) {
    tray_.Install(hwnd_, tooltip);
}

void OverlayWindow::RemoveTrayIcon() {
    tray_.Remove();
}

void OverlayWindow::ShowStartup(int durationMs) {
    durationMs_ = durationMs;
    shownAt_ = std::chrono::steady_clock::now();
    visible_ = true;

    const int width = GetSystemMetrics(SM_CXSCREEN);
    const int height = GetSystemMetrics(SM_CYSCREEN);
    SetWindowPos(hwnd_, HWND_TOPMOST, 0, 0, width, height, SWP_NOACTIVATE | SWP_SHOWWINDOW);
    SetTimer(hwnd_, kAnimationTimer, 16, nullptr);
    InvalidateRect(hwnd_, nullptr, FALSE);
}

void OverlayWindow::RegisterClass() {
    WNDCLASSEXW wc{};
    wc.cbSize = sizeof(wc);
    wc.lpfnWndProc = StaticWndProc;
    wc.hInstance = instance_;
    wc.hCursor = LoadCursorW(nullptr, IDC_ARROW);
    wc.hIcon = LoadIconW(nullptr, IDI_APPLICATION);
    wc.hbrBackground = reinterpret_cast<HBRUSH>(GetStockObject(BLACK_BRUSH));
    wc.lpszClassName = kClassName;
    RegisterClassExW(&wc);
}

LRESULT CALLBACK OverlayWindow::StaticWndProc(HWND hwnd, UINT message, WPARAM wParam, LPARAM lParam) {
    OverlayWindow* self = nullptr;
    if (message == WM_NCCREATE) {
        const auto* create = reinterpret_cast<CREATESTRUCTW*>(lParam);
        self = static_cast<OverlayWindow*>(create->lpCreateParams);
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(self));
        self->hwnd_ = hwnd;
    } else {
        self = reinterpret_cast<OverlayWindow*>(GetWindowLongPtrW(hwnd, GWLP_USERDATA));
    }
    return self ? self->WndProc(message, wParam, lParam) : DefWindowProcW(hwnd, message, wParam, lParam);
}

LRESULT OverlayWindow::WndProc(UINT message, WPARAM wParam, LPARAM lParam) {
    switch (message) {
        case WM_TIMER:
            if (wParam == kAnimationTimer) {
                if (Progress(shownAt_, durationMs_) >= 1.0f) {
                    KillTimer(hwnd_, kAnimationTimer);
                    visible_ = false;
                    ShowWindow(hwnd_, SW_HIDE);
                } else {
                    InvalidateRect(hwnd_, nullptr, FALSE);
                }
                return 0;
            }
            break;

        case WM_PAINT:
            Paint();
            return 0;

        case WM_ERASEBKGND:
            return 1;

        case jarvis::system::TrayIcon::Message:
            if (LOWORD(lParam) == WM_RBUTTONUP || LOWORD(lParam) == WM_CONTEXTMENU) {
                ShowTrayMenu();
            } else if (LOWORD(lParam) == WM_LBUTTONDBLCLK && onActivate_) {
                onActivate_();
            }
            return 0;

        case WM_COMMAND:
            switch (LOWORD(wParam)) {
                case kCommandLaunch:
                    if (onActivate_) {
                        onActivate_();
                    }
                    return 0;
                case kCommandShow:
                    ShowStartup(4200);
                    return 0;
                case kCommandReload:
                    if (onReload_) {
                        onReload_();
                    }
                    return 0;
                case kCommandExit:
                    if (onExit_) {
                        onExit_();
                    }
                    return 0;
            }
            break;

        case WM_DESTROY:
            RemoveTrayIcon();
            return 0;
    }

    return DefWindowProcW(hwnd_, message, wParam, lParam);
}

void OverlayWindow::ShowTrayMenu() {
    POINT point{};
    GetCursorPos(&point);
    tray_.ShowMenu(hwnd_, point);
}

void OverlayWindow::Paint() {
    PAINTSTRUCT ps{};
    HDC hdc = BeginPaint(hwnd_, &ps);
    RECT rect{};
    GetClientRect(hwnd_, &rect);

    HDC memoryDc = CreateCompatibleDC(hdc);
    HBITMAP bitmap = CreateCompatibleBitmap(hdc, rect.right - rect.left, rect.bottom - rect.top);
    HGDIOBJ previous = SelectObject(memoryDc, bitmap);

    Gdiplus::Graphics graphics(memoryDc);
    graphics.SetSmoothingMode(Gdiplus::SmoothingModeHighQuality);
    DrawScene(graphics, rect);

    BitBlt(hdc, 0, 0, rect.right - rect.left, rect.bottom - rect.top, memoryDc, 0, 0, SRCCOPY);
    SelectObject(memoryDc, previous);
    DeleteObject(bitmap);
    DeleteDC(memoryDc);
    EndPaint(hwnd_, &ps);
}

void OverlayWindow::DrawScene(Gdiplus::Graphics& graphics, const RECT& rect) {
    const int width = rect.right - rect.left;
    const int height = rect.bottom - rect.top;
    const float progress = Progress(shownAt_, durationMs_);
    const float pulse = 0.5f + 0.5f * std::sin(progress * 28.0f);

    Gdiplus::SolidBrush background(ColorArgb(214, 2, 8, 10));
    graphics.FillRectangle(&background, 0, 0, width, height);

    Gdiplus::Pen gridPen(ColorArgb(28, 54, 232, 255), 1.0f);
    for (int x = 0; x < width; x += 44) {
        graphics.DrawLine(&gridPen, x, 0, x, height);
    }
    for (int y = 0; y < height; y += 44) {
        graphics.DrawLine(&gridPen, 0, y, width, y);
    }

    const int panelWidth = std::min(760, width - 96);
    const int panelHeight = std::min(420, height - 96);
    const int panelX = (width - panelWidth) / 2;
    const int panelY = (height - panelHeight) / 2;
    Gdiplus::Rect panel(panelX, panelY, panelWidth, panelHeight);

    Gdiplus::SolidBrush panelBrush(ColorArgb(178, 7, 18, 22));
    Gdiplus::Pen panelPen(ColorArgb(170, 54, 232, 255), 2.0f);
    graphics.FillRectangle(&panelBrush, panel);
    graphics.DrawRectangle(&panelPen, panel);

    const int centerX = width / 2;
    const int centerY = panelY + 180;
    const int baseRadius = 54 + static_cast<int>(pulse * 8);

    for (int ring = 0; ring < 5; ++ring) {
        const int radius = baseRadius + ring * 34;
        const BYTE alpha = static_cast<BYTE>(150 - ring * 20);
        Gdiplus::Pen ringPen(ColorArgb(alpha, ring % 2 == 0 ? 54 : 255, ring % 2 == 0 ? 232 : 209, ring % 2 == 0 ? 255 : 102), 2.0f);
        graphics.DrawEllipse(&ringPen, centerX - radius, centerY - radius, radius * 2, radius * 2);
    }

    Gdiplus::SolidBrush coreBrush(ColorArgb(230, 190, 252, 255));
    Gdiplus::Pen corePen(ColorArgb(255, 255, 255, 255), 4.0f);
    graphics.FillEllipse(&coreBrush, centerX - 62, centerY - 62, 124, 124);
    graphics.DrawEllipse(&corePen, centerX - 62, centerY - 62, 124, 124);

    Gdiplus::FontFamily fontFamily(L"Segoe UI");
    Gdiplus::Font titleFont(&fontFamily, 42.0f, Gdiplus::FontStyleBold, Gdiplus::UnitPixel);
    Gdiplus::Font smallFont(&fontFamily, 18.0f, Gdiplus::FontStyleBold, Gdiplus::UnitPixel);
    Gdiplus::Font statusFont(&fontFamily, 22.0f, Gdiplus::FontStyleRegular, Gdiplus::UnitPixel);
    Gdiplus::SolidBrush textBrush(ColorArgb(245, 232, 254, 255));
    Gdiplus::SolidBrush accentBrush(ColorArgb(255, 255, 209, 102));
    Gdiplus::SolidBrush cyanBrush(ColorArgb(255, 54, 232, 255));

    graphics.DrawString(L"JARVIS", -1, &titleFont, Gdiplus::PointF(static_cast<float>(panelX + 32), static_cast<float>(panelY + 28)), &textBrush);
    graphics.DrawString(L"WORKSPACE INITIALIZATION", -1, &smallFont, Gdiplus::PointF(static_cast<float>(panelX + 34), static_cast<float>(panelY + 86)), &accentBrush);
    graphics.DrawString(L"Spotify, Chrome, AyuGram, VS Code, Android Studio", -1, &statusFont, Gdiplus::PointF(static_cast<float>(panelX + 34), static_cast<float>(panelY + panelHeight - 74)), &textBrush);

    const int waveY = panelY + panelHeight - 118;
    const int waveX = panelX + panelWidth - 320;
    for (int i = 0; i < 46; ++i) {
        const float phase = progress * 40.0f + static_cast<float>(i) * 0.55f;
        const int barHeight = 10 + static_cast<int>((0.5f + 0.5f * std::sin(phase)) * 58.0f);
        Gdiplus::Pen barPen(ColorArgb(210, 54, 232, 255), 3.0f);
        const int x = waveX + i * 6;
        graphics.DrawLine(&barPen, x, waveY - barHeight / 2, x, waveY + barHeight / 2);
    }

    Gdiplus::Pen scanPen(ColorArgb(70, 255, 255, 255), 1.0f);
    const int scanY = static_cast<int>(height * progress);
    graphics.DrawLine(&scanPen, 0, scanY, width, scanY);
}

}  // namespace jarvis::ui
