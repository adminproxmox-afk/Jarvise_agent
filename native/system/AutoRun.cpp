#include "system/AutoRun.h"

#include <windows.h>

#include "system/Logger.h"

namespace jarvis::system {

namespace {
constexpr const wchar_t* kRunKey = L"Software\\Microsoft\\Windows\\CurrentVersion\\Run";
}

bool AutoRun::Install(const std::wstring& appName, const std::wstring& executablePath) {
    HKEY key{};
    if (RegCreateKeyExW(HKEY_CURRENT_USER, kRunKey, 0, nullptr, 0, KEY_SET_VALUE, nullptr, &key, nullptr) != ERROR_SUCCESS) {
        Logger::Error(L"Failed to open HKCU Run key.");
        return false;
    }

    const std::wstring value = L"\"" + executablePath + L"\"";
    const auto bytes = static_cast<DWORD>((value.size() + 1) * sizeof(wchar_t));
    const LONG result = RegSetValueExW(key, appName.c_str(), 0, REG_SZ, reinterpret_cast<const BYTE*>(value.c_str()), bytes);
    RegCloseKey(key);

    if (result != ERROR_SUCCESS) {
        Logger::Error(L"Failed to install autorun registry value.");
        return false;
    }
    Logger::Info(L"Autorun installed in HKCU Run.");
    return true;
}

bool AutoRun::Remove(const std::wstring& appName) {
    HKEY key{};
    if (RegOpenKeyExW(HKEY_CURRENT_USER, kRunKey, 0, KEY_SET_VALUE, &key) != ERROR_SUCCESS) {
        return false;
    }
    const LONG result = RegDeleteValueW(key, appName.c_str());
    RegCloseKey(key);
    return result == ERROR_SUCCESS;
}

}  // namespace system
