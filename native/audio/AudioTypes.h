#pragma once

#include <vector>

namespace jarvis::audio {

struct AudioChunk {
    std::vector<float> samples;
    int sampleRate = 48000;
};

}  // namespace jarvis::audio
