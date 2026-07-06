#include "launcher/WorkspaceLauncher.h"

#include <utility>

#include <windows.h>

#include "system/Logger.h"
#include "system/ProcessUtils.h"

namespace jarvis::launcher {

WorkspaceLauncher::WorkspaceLauncher(config::WorkspaceConfig settings, spotify::SpotifyController& spotify)
    : settings_(std::move(settings)), spotify_(spotify) {}

void WorkspaceLauncher::LaunchAll() {
    spotify_.LaunchAndPlayTrack();

    LaunchApp(settings_.chrome);
    LaunchApp(settings_.ayugram);
    LaunchApp(settings_.vscode);
    LaunchApp(settings_.androidStudio);
}

bool WorkspaceLauncher::LaunchApp(const config::AppLaunchConfig& app) {
    if (!app.enabled) {
        jarvis::system::Logger::Info(L"App disabled: " + app.id);
        return true;
    }

    if (app.skipIfRunning && !app.processName.empty() && jarvis::system::ProcessUtils::IsProcessRunning(app.processName)) {
        jarvis::system::Logger::Info(L"App already running: " + app.processName);
        return true;
    }

    const std::wstring command = jarvis::system::ProcessUtils::ResolveCommand(app.command, app.pathCandidates);
    jarvis::system::LaunchRequest request;
    request.command = command;
    request.showCommand = SW_SHOWNORMAL;
    return jarvis::system::ProcessUtils::Launch(request);
}

}  // namespace jarvis::launcher
