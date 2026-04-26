/* E.C.H.O. browser frontend.
 *
 *   - WebSocket client (auto-reconnect)
 *   - Browser mic capture via getUserMedia + AudioWorklet
 *   - Energy-based VAD: accumulate while speech-active, send PCM on silence
 *   - Streaming TTS playback via <audio>
 *   - Renders bus events into the feed columns
 */

// ──────────────────────────────────────────────────────────────────────
// State
// ──────────────────────────────────────────────────────────────────────
const STATE = {
    ws: null,
    audioCtx: null,
    micStream: null,
    micNode: null,
    rmsThreshold: 0.012,    // browser mic levels are usually higher than pyaudio's
    silenceFramesNeeded: 22, // ~700ms of silence at 32ms frames
    minUtteranceFrames: 16,  // ~512ms minimum to bother sending
    maxUtteranceFrames: 480, // ~15s max
    speechBuffer: [],        // Float32Array chunks while in active speech
    silenceFrames: 0,
    listening: false,
    lastTtsAudio: null,
};

const $ = (id) => document.getElementById(id);

// ──────────────────────────────────────────────────────────────────────
// WebSocket
// ──────────────────────────────────────────────────────────────────────
function connectWs() {
    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${location.host}/ws`);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
        STATE.ws = ws;
        setStatus("online", "online");
        ws.send(JSON.stringify({type: "audio_meta", sample_rate: 16000}));
    };

    ws.onclose = () => {
        STATE.ws = null;
        setStatus("error", "disconnected — retrying…");
        setTimeout(connectWs, 1500);
    };

    ws.onerror = () => {};

    ws.onmessage = (evt) => {
        if (typeof evt.data !== "string") return;
        let m;
        try { m = JSON.parse(evt.data); } catch { return; }
        handleEvent(m);
    };
}

function handleEvent(m) {
    switch (m.type) {
        case "status":
            setStatus(m.value, m.value);
            break;
        case "audio.rms":
            updateRms(m.value);
            break;
        case "transcript.final":
            addFeedItem("transcript-list", m.text);
            break;
        case "memory.extracted":
            addFeedItem("memory-list", m.content);
            break;
        case "action_item.extracted":
            addFeedItem("action-list", m.content);
            break;
        case "response.start":
            setResponse("");
            break;
        case "response.chunk":
            appendResponse(m.text);
            break;
        case "response.end":
            // nothing — text already in place
            break;
        case "response.tts_chunk_b64":
            playTtsB64(m.data);
            break;
    }
}

// ──────────────────────────────────────────────────────────────────────
// Status / RMS / response / feed rendering
// ──────────────────────────────────────────────────────────────────────
function setStatus(cls, label) {
    const pill = document.querySelector(".status-pill");
    pill.className = "status-pill " + cls;
    $("status-text").textContent = label;
}

function updateRms(v) {
    const pct = Math.min(100, Math.max(0, v * 200));
    $("rms-fill").style.width = pct + "%";
    // also pulse the rings
    document.querySelectorAll(".ring").forEach((r, i) => {
        const factor = 1 + v * (0.06 - i * 0.012);
        r.style.transform = `scale(${factor})`;
    });
}

function setResponse(txt) {
    const el = $("response");
    el.textContent = txt;
    el.classList.toggle("empty", !txt);
}

function appendResponse(txt) {
    const el = $("response");
    el.textContent = (el.textContent || "") + txt;
    el.classList.remove("empty");
}

function addFeedItem(listId, text) {
    if (!text) return;
    const ul = $(listId);
    const li = document.createElement("li");
    li.textContent = text;
    li.className = "new";
    ul.insertBefore(li, ul.firstChild);
    // Cap list length so DOM doesn't grow forever
    while (ul.children.length > 30) ul.removeChild(ul.lastChild);
}

// ──────────────────────────────────────────────────────────────────────
// Browser mic — getUserMedia + AudioWorklet
// ──────────────────────────────────────────────────────────────────────
async function startMic() {
    if (STATE.micStream) return;
    try {
        // 16kHz target; browsers may force their device rate; we resample.
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });
        STATE.micStream = stream;

        // AudioContext at native rate; our processor downsamples to 16k.
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        STATE.audioCtx = ctx;

        await ctx.audioWorklet.addModule("/static/mic-worklet.js");

        const source = ctx.createMediaStreamSource(stream);
        const node = new AudioWorkletNode(ctx, "mic-frame-processor", {
            processorOptions: {sourceSampleRate: ctx.sampleRate, targetSampleRate: 16000}
        });

        node.port.onmessage = (e) => onMicFrame(e.data);
        source.connect(node);
        // Don't connect to destination — we don't want to hear ourselves.

        STATE.micNode = node;
        STATE.listening = true;
        $("mic-btn").classList.add("active");
        console.log("[mic] started @", ctx.sampleRate, "Hz, downsampled to 16000");
    } catch (e) {
        console.error("[mic] failed:", e);
        alert("Mic access denied or unavailable. Check browser permissions.");
    }
}

function stopMic() {
    if (STATE.micStream) {
        STATE.micStream.getTracks().forEach(t => t.stop());
        STATE.micStream = null;
    }
    if (STATE.micNode) { STATE.micNode.disconnect(); STATE.micNode = null; }
    if (STATE.audioCtx) { STATE.audioCtx.close(); STATE.audioCtx = null; }
    STATE.listening = false;
    STATE.speechBuffer = [];
    STATE.silenceFrames = 0;
    $("mic-btn").classList.remove("active");
}

// Called on each downsampled mic frame (Float32Array, ~32ms at 16kHz)
function onMicFrame(frame) {
    // Compute RMS for visualization
    let sum = 0;
    for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
    const rms = Math.sqrt(sum / frame.length);
    updateRms(rms);

    const isSpeech = rms > STATE.rmsThreshold;

    if (isSpeech) {
        STATE.speechBuffer.push(frame);
        STATE.silenceFrames = 0;
    } else if (STATE.speechBuffer.length > 0) {
        STATE.speechBuffer.push(frame);  // keep some trailing silence
        STATE.silenceFrames++;
    }

    const longSilence = STATE.silenceFrames >= STATE.silenceFramesNeeded
                       && STATE.speechBuffer.length >= STATE.minUtteranceFrames;
    const capHit = STATE.speechBuffer.length >= STATE.maxUtteranceFrames;

    if (longSilence || capHit) {
        flushUtterance();
    }
}

function flushUtterance() {
    const chunks = STATE.speechBuffer;
    STATE.speechBuffer = [];
    STATE.silenceFrames = 0;
    if (!chunks.length) return;

    // Concat all Float32 chunks
    let total = 0;
    for (const c of chunks) total += c.length;
    const merged = new Float32Array(total);
    let off = 0;
    for (const c of chunks) { merged.set(c, off); off += c.length; }

    if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
        STATE.ws.send(merged.buffer);
        console.log(`[mic] sent ${total} samples (${(total/16000).toFixed(1)}s)`);
    }
}

// ──────────────────────────────────────────────────────────────────────
// TTS playback — base64 -> blob -> <audio>
// ──────────────────────────────────────────────────────────────────────
function playTtsB64(b64) {
    try {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes], {type: "audio/mpeg"});
        const url = URL.createObjectURL(blob);

        // Stop any previous playback first
        if (STATE.lastTtsAudio) {
            try { STATE.lastTtsAudio.pause(); } catch (e) {}
            STATE.lastTtsAudio = null;
        }
        const audio = new Audio(url);
        audio.onended = () => URL.revokeObjectURL(url);
        STATE.lastTtsAudio = audio;
        audio.play().catch(e => console.warn("[tts] play failed:", e));
    } catch (e) {
        console.error("[tts] decode failed:", e);
    }
}

// ──────────────────────────────────────────────────────────────────────
// Input handling
// ──────────────────────────────────────────────────────────────────────
$("input-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("input").value.trim();
    if (!text) return;
    if (!STATE.ws || STATE.ws.readyState !== WebSocket.OPEN) return;
    STATE.ws.send(JSON.stringify({type: "submit", text}));
    $("input").value = "";
});

$("mic-btn").addEventListener("click", () => {
    if (STATE.listening) stopMic();
    else startMic();
});

// ──────────────────────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────────────────────
connectWs();
console.log("[echo] web UI booted");
