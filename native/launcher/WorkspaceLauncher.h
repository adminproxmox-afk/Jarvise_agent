#pragma once

#include <string>

#include "config/Config.h"
#include "spotify/SpotifyController.h"

namespace jarvis::launcher {

class WorkspaceLauncher {
public:
    WorkspaceLauncher(config::WorkspaceConfig settings, spotify::SpotifyController& spotify);

    void LaunchAll();

private:
    bool LaunchApp(const config::AppLaunchConfig& app);

    config::WorkspaceConfig settings_;
    spotify::SpotifyController& spotify_;
};

}  // namespace jarvis::launcher
