#pragma once

#include "config/Config.h"

namespace jarvis::spotify {

class SpotifyController {
public:
    explicit SpotifyController(config::SpotifyConfig settings);

    bool LaunchAndPlayTrack();

private:
    void SendMediaPlayKey() const;

    config::SpotifyConfig settings_;
};

}  // namespace jarvis::spotify
