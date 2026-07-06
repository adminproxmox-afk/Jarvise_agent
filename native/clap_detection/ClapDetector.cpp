#include "clap_detection/ClapDetector.h"

#include <algorithm>
#include <cmath>

#include "system/Logger.h"

namespace jarvis::clap_detection {

ClapDetector::ClapDetector(config::ClapConfig settings) : settings_(settings) {}

void ClapDetector::UpdateSettings(config::ClapConfig settings) {
    std::lock_guard lock(mutex_);
    settings_ = settings;
}

void ClapDetector::SetDoubleClapCallback(Callback callback) {
    std::lock_guard lock(mutex_);
    callback_ = std::move(callback);
}

void ClapDetector::Process(const audio::AudioChunk& chunk) {
    if (chunk.samples.empty()) {
        return;
    }

    Callback callback;
    bool fire = false;
    const Metrics metrics = ComputeMetrics(chunk.samples);
    const auto now = std::chrono::steady_clock::now();

    {
        std::lock_guard lock(mutex_);
        if (!settings_.enabled || now < cooldownUntil_) {
            return;
        }

        const double dynamicThreshold = std::max(settings_.sensitivity, noiseFloor_ * settings_.noiseFloorMultiplier);
        const bool quietEnoughForNoiseLearning = metrics.rms < dynamicThreshold * 0.55;
        if (settings_.adaptiveNoise && quietEnoughForNoiseLearning) {
            noiseFloor_ = (noiseFloor_ * 0.985) + (metrics.rms * 0.015);
        }

        const auto gap = std::chrono::duration_cast<std::chrono::milliseconds>(now - lastClap_).count();
        const bool clap =
            gap >= settings_.minClapGapMs &&
            metrics.rms >= dynamicThreshold &&
            metrics.peak >= dynamicThreshold * 1.12 &&
            metrics.sharpness >= dynamicThreshold * 0.72;

        if (!clap) {
            return;
        }

        lastClap_ = now;
        clapWindow_.erase(
            std::remove_if(
                clapWindow_.begin(),
                clapWindow_.end(),
                [&](const auto& stamp) {
                    return std::chrono::duration_cast<std::chrono::milliseconds>(now - stamp).count() >
                           settings_.doubleClapWindowMs;
                }),
            clapWindow_.end());
        clapWindow_.push_back(now);

        jarvis::system::Logger::Info(L"Clap detected.");
        if (clapWindow_.size() >= 2) {
            clapWindow_.clear();
            cooldownUntil_ = now + std::chrono::milliseconds(settings_.cooldownMs);
            callback = callback_;
            fire = true;
        }
    }

    if (fire && callback) {
        jarvis::system::Logger::Info(L"Double clap detected.");
        callback();
    }
}

ClapDetector::Metrics ClapDetector::ComputeMetrics(const std::vector<float>& samples) {
    double sumSquares = 0.0;
    double peak = 0.0;
    double sharpness = 0.0;
    float previous = samples.front();

    for (const float sample : samples) {
        const double absolute = std::abs(sample);
        sumSquares += static_cast<double>(sample) * static_cast<double>(sample);
        peak = std::max(peak, absolute);
        sharpness = std::max(sharpness, static_cast<double>(std::abs(sample - previous)));
        previous = sample;
    }

    return {
        std::sqrt(sumSquares / static_cast<double>(samples.size())),
        peak,
        sharpness,
    };
}

config::ClapConfig ClapDetector::SettingsSnapshot() const {
    std::lock_guard lock(mutex_);
    return settings_;
}

}  // namespace jarvis::clap_detection
