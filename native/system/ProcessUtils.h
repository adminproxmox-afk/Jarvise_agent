#pragma once

#include <string>
#include <vector>

namespace jarvis::system {

struct LaunchRequest {
    std::wstring command;
    std::wstring arguments;
    std::wstring workingDirectory;
    int showCommand = 1;
};

class ProcessUtils {
public:
    static std::wstring ExecutablePath();
    static std::wstring ExecutableDirectory();
    static bool IsProcessRunning(const std::wstring& processName);
    static bool Launch(const LaunchRequest& request);
    static bool LaunchUri(const std::wstring& uri);
    static std::wstring ResolveCommand(
        const std::wstring& command,
        const std::vector<std::wstring>& pathCandidates = {});
};

}  // namespace system
