/* AudioWorklet processor — runs in the audio thread.
 *
 * Browser mic typically runs at 44.1kHz or 48kHz. We downsample to 16kHz
 * (whisper's native rate) here so the main thread doesn't have to. We also
 * accumulate to ~32ms frames (512 samples @ 16kHz) before posting up.
 */

class MicFrameProcessor extends AudioWorkletProcessor {
    constructor(options) {
        super();
        const opts = options.processorOptions || {};
        this.sourceSr = opts.sourceSampleRate || sampleRate;
        this.targetSr = opts.targetSampleRate || 16000;
        this.ratio = this.sourceSr / this.targetSr;

        // Buffer downsampled samples until we have FRAME_SAMPLES, then post.
        this.FRAME_SAMPLES = 512;     // ~32ms at 16kHz
        this.buf = new Float32Array(this.FRAME_SAMPLES);
        this.bufFill = 0;

        // Resampling state — fractional read index across process() calls
        this.readIdx = 0;
    }

    process(inputs) {
        const input = inputs[0];
        if (!input || !input[0]) return true;
        const ch = input[0];  // mono

        // Linear interpolation downsample (good enough for STT)
        // Continue from `this.readIdx` across calls.
        let i = this.readIdx;
        while (i < ch.length) {
            const i0 = Math.floor(i);
            const i1 = Math.min(i0 + 1, ch.length - 1);
            const frac = i - i0;
            const sample = ch[i0] * (1 - frac) + ch[i1] * frac;

            this.buf[this.bufFill++] = sample;

            if (this.bufFill >= this.FRAME_SAMPLES) {
                // Post a copy so we can reuse buf
                this.port.postMessage(this.buf.slice(0));
                this.bufFill = 0;
            }
            i += this.ratio;
        }
        // Carry leftover fractional index into next process() call
        this.readIdx = i - ch.length;
        return true;
    }
}

registerProcessor("mic-frame-processor", MicFrameProcessor);
