#pragma once

#include <atomic>
#include <chrono>
#include <functional>
#include <mutex>
#include <vector>

#include "audio/AudioTypes.h"
#include "config/Config.h"

namespace jarvis::clap_detection {

class ClapDetector {
public:
    using Callback = std::function<void()>;

    explicit ClapDetector(config::ClapConfig settings);

    void UpdateSettings(config::ClapConfig settings);
    void SetDoubleClapCallback(Callback callback);
    void Process(const audio::AudioChunk& chunk);

private:
    struct Metrics {
        double rms = 0.0;
        double peak = 0.0;
        double sharpness = 0.0;
    };

    static Metrics ComputeMetrics(const std::vector<float>& samples);

    config::ClapConfig SettingsSnapshot() const;

    mutable std::mutex mutex_;
    config::ClapConfig settings_;
    Callback callback_;
    double noiseFloor_{0.025};
    std::chrono::steady_clock::time_point lastClap_{};
    std::chrono::steady_clock::time_point cooldownUntil_{};
    std::vector<std::chrono::steady_clock::time_point> clapWindow_;
};

}  // namespace jarvis::clap_detection
