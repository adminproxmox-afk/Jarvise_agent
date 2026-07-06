#include "system/ProcessUtils.h"

#include <filesystem>
#include <vector>

#include <windows.h>
#include <shellapi.h>
#include <tlhelp32.h>

#include "system/Logger.h"
#include "system/StringUtils.h"

namespace jarvis::system {

std::wstring ProcessUtils::ExecutablePath() {
    std::wstring buffer(MAX_PATH, L'\0');
    DWORD length = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
    while (length == buffer.size()) {
        buffer.resize(buffer.size() * 2);
        length = GetModuleFileNameW(nullptr, buffer.data(), static_cast<DWORD>(buffer.size()));
    }
    buffer.resize(length);
    return buffer;
}

std::wstring ProcessUtils::ExecutableDirectory() {
    return std::filesystem::path(ExecutablePath()).parent_path().wstring();
}

bool ProcessUtils::IsProcessRunning(const std::wstring& processName) {
    const std::wstring needle = ToLower(processName);
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) {
        return false;
    }

    PROCESSENTRY32W entry{};
    entry.dwSize = sizeof(entry);
    bool found = false;
    if (Process32FirstW(snapshot, &entry)) {
        do {
            if (ToLower(entry.szExeFile) == needle) {
                found = true;
                break;
            }
        } while (Process32NextW(snapshot, &entry));
    }
    CloseHandle(snapshot);
    return found;
}

bool ProcessUtils::Launch(const LaunchRequest& request) {
    SHELLEXECUTEINFOW exec{};
    exec.cbSize = sizeof(exec);
    exec.fMask = SEE_MASK_NOCLOSEPROCESS;
    exec.lpVerb = L"open";
    exec.lpFile = request.command.c_str();
    exec.lpParameters = request.arguments.empty() ? nullptr : request.arguments.c_str();
    exec.lpDirectory = request.workingDirectory.empty() ? nullptr : request.workingDirectory.c_str();
    exec.nShow = request.showCommand;

    if (!ShellExecuteExW(&exec)) {
        Logger::Error(L"Launch failed: " + request.command);
        return false;
    }
    if (exec.hProcess) {
        CloseHandle(exec.hProcess);
    }
    Logger::Info(L"Launched: " + request.command);
    return true;
}

bool ProcessUtils::LaunchUri(const std::wstring& uri) {
    LaunchRequest request;
    request.command = uri;
    request.showCommand = SW_SHOWNORMAL;
    return Launch(request);
}

std::wstring ProcessUtils::ResolveCommand(
    const std::wstring& command,
    const std::vector<std::wstring>& pathCandidates) {
    for (const auto& rawCandidate : pathCandidates) {
        const auto candidate = ExpandEnvironmentStringsSafe(rawCandidate);
        if (std::filesystem::exists(candidate)) {
            return candidate;
        }
    }

    const auto expanded = ExpandEnvironmentStringsSafe(command);
    if (std::filesystem::exists(expanded)) {
        return expanded;
    }
    return expanded;
}

}  // namespace system
