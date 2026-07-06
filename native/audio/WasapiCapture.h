#pragma once

#include <atomic>
#include <functional>
#include <thread>

#include "audio/AudioTypes.h"

namespace jarvis::audio {

class WasapiCapture {
public:
    using Callback = std::function<void(const AudioChunk&)>;

    WasapiCapture() = default;
    ~WasapiCapture();

    WasapiCapture(const WasapiCapture&) = delete;
    WasapiCapture& operator=(const WasapiCapture&) = delete;

    bool Start(Callback callback);
    void Stop();

private:
    void CaptureThread();
    Callback callback_;
    std::thread thread_;
    std::atomic_bool running_{false};
};

}  // namespace jarvis::audio
