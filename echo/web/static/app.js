/* E.C.H.O. browser frontend.
 *
 *   - Three.js dot-globe (./globe.js)
 *   - Sleep/wake state machine (spacebar / click to wake; 5min idle -> sleep)
 *   - WebSocket client (auto-reconnect)
 *   - Browser mic capture + VAD (mic-worklet.js) — only active while awake
 *   - Streaming TTS playback via <audio>
 *   - Typewriter rendering for response.chunk events
 */

import { DotGlobe } from "/static/globe.js";

const SLEEP_TIMEOUT_MS = 5 * 60 * 1000;   // 5 min idle
const TYPEWRITER_MS_PER_CHAR = 22;

// ──────────────────────────────────────────────────────────────────────
// State
// ──────────────────────────────────────────────────────────────────────
const STATE = {
    ws: null,
    audioCtx: null,
    micStream: null,
    micNode: null,
    rmsThreshold: 0.012,
    silenceFramesNeeded: 22,
    minUtteranceFrames: 16,
    maxUtteranceFrames: 480,
    speechBuffer: [],
    silenceFrames: 0,
    // Rolling pre-roll buffer — keep the last N frames so that when speech
    // is detected we can prepend them. Energy VAD always misses the first
    // 100-200ms of an utterance (consonants are quiet); without pre-roll
    // whisper hears "at time is it" instead of "what time is it".
    preRollBuffer: [],
    PRE_ROLL_FRAMES: 6,        // ~192ms at 32ms frames
    listening: false,
    sleeping: true,
    lastInteraction: Date.now(),
    // True while ECHO has paused the mic for external media (YouTube etc.).
    // User clicks the mic button to resume.
    micPausedForMedia: false,
    twTimer: null,
    twQueue: "",
    // ── streaming TTS audio queue ──
    ttsQueue: [],            // pending blob URLs waiting to play
    ttsCurrent: null,        // currently playing Audio element
    ttsActive: false,        // true while audio is playing or queued
    bargeInDebounce: 0,      // ticks remaining before another barge-in fires
    BARGE_IN_DEBOUNCE: 30,   // ~1s of silence before next barge-in (32ms frames)
};

const $ = (id) => document.getElementById(id);

// ──────────────────────────────────────────────────────────────────────
// Globe
// ──────────────────────────────────────────────────────────────────────
const globe = new DotGlobe($("globe-mount"));

// ──────────────────────────────────────────────────────────────────────
// Sleep / wake state machine
// ──────────────────────────────────────────────────────────────────────
function setSleeping(sleeping) {
    STATE.sleeping = sleeping;
    globe.setSleeping(sleeping);
    document.getElementById("globe-stage").classList.toggle("sleeping", sleeping);
    if (sleeping) {
        $("sub-status").textContent = "SLEEPING";
        stopMic();
    } else {
        $("sub-status").textContent = "ONLINE";
        STATE.lastInteraction = Date.now();
        // Best-effort start mic — browser may need user gesture; if we got
        // here via a click/spacebar, that satisfies the gesture requirement.
        startMic().catch(() => {});
    }
    // Tell server about state change
    if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
        STATE.ws.send(JSON.stringify({type: sleeping ? "sleep" : "wake"}));
    }
}

function bumpInteraction() { STATE.lastInteraction = Date.now(); }

// Idle-to-sleep monitor
setInterval(() => {
    if (!STATE.sleeping && Date.now() - STATE.lastInteraction > SLEEP_TIMEOUT_MS) {
        setSleeping(true);
    }
}, 5000);

// Wake on spacebar (when sleeping and focus is NOT on the input)
document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && STATE.sleeping
        && document.activeElement !== $("input")) {
        e.preventDefault();
        setSleeping(false);
    }
});
// Wake on click of the globe area
$("globe-stage").addEventListener("click", () => {
    if (STATE.sleeping) setSleeping(false);
});

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
            $("globe-stage").classList.remove("online", "thinking", "speaking", "listening");
            if (m.value && m.value !== "sleeping") $("globe-stage").classList.add(m.value);
            $("sub-status").textContent = (m.value || "online").toUpperCase();
            break;
        case "audio.rms":
            // Backend (Python AudioCapture in Tkinter mode) publishes this;
            // in pure web mode it's the browser worklet that updates RMS.
            // We accept either — last writer wins.
            updateRms(m.value);
            break;
        case "transcript.final":
            addFeedItem("transcript-list", m.text);
            bumpInteraction();
            break;
        case "memory.extracted":
            addFeedItem("memory-list", m.content);
            break;
        case "action_item.extracted":
            addFeedItem("action-list", m.content);
            break;
        case "response.start":
            twReset();
            break;
        case "response.chunk":
            twAppend(m.text);
            break;
        case "response.end":
            // Typewriter finishes draining naturally
            break;
        case "response.tts_chunk_b64":
            ttsEnqueue(m.data);
            break;
        case "tts.stopped":
            // Server confirmed cancellation (e.g. our barge-in arrived first
            // OR a new submit replaced an in-flight stream)
            ttsStopAll();
            break;
        case "mic.pause":
            // ECHO triggered media (YouTube etc). Stop listening so we
            // don't transcribe the song back to ourselves.
            console.log(`[mic] paused by server: ${m.reason}`);
            STATE.micPausedForMedia = true;
            stopMic();
            $("sub-status").textContent = "MUTED FOR MEDIA — CLICK MIC TO RESUME";
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
    globe.setRms(Math.max(0, Math.min(1, v * 4)));
    const pct = Math.min(100, Math.max(0, v * 200));
    $("rms-fill").style.width = pct + "%";
}

// ── Typewriter ──
function twReset() {
    if (STATE.twTimer) { clearInterval(STATE.twTimer); STATE.twTimer = null; }
    STATE.twQueue = "";
    $("response").textContent = "";
    $("response").classList.add("empty");
}

function twAppend(text) {
    STATE.twQueue += text;
    $("response").classList.remove("empty");
    if (!STATE.twTimer) {
        STATE.twTimer = setInterval(() => {
            if (!STATE.twQueue.length) {
                clearInterval(STATE.twTimer);
                STATE.twTimer = null;
                return;
            }
            // Type 1-3 chars per tick for natural-feeling pace
            const n = Math.min(STATE.twQueue.length, 1 + Math.floor(Math.random() * 3));
            $("response").textContent += STATE.twQueue.slice(0, n);
            STATE.twQueue = STATE.twQueue.slice(n);
        }, TYPEWRITER_MS_PER_CHAR);
    }
}

function addFeedItem(listId, text) {
    if (!text) return;
    const ul = $(listId);
    const li = document.createElement("li");
    li.textContent = text;
    li.className = "new";
    ul.insertBefore(li, ul.firstChild);
    while (ul.children.length > 30) ul.removeChild(ul.lastChild);
}

// ──────────────────────────────────────────────────────────────────────
// Browser mic — getUserMedia + AudioWorklet
// ──────────────────────────────────────────────────────────────────────
async function startMic() {
    if (STATE.micStream || STATE.sleeping) return;
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true,
            }
        });
        STATE.micStream = stream;

        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        STATE.audioCtx = ctx;

        await ctx.audioWorklet.addModule("/static/mic-worklet.js");

        const source = ctx.createMediaStreamSource(stream);
        const node = new AudioWorkletNode(ctx, "mic-frame-processor", {
            processorOptions: {sourceSampleRate: ctx.sampleRate, targetSampleRate: 16000}
        });
        node.port.onmessage = (e) => onMicFrame(e.data);
        source.connect(node);

        STATE.micNode = node;
        STATE.listening = true;
        $("mic-btn").classList.add("active");
        console.log(`[mic] started @ ${ctx.sampleRate}Hz -> 16000Hz`);
    } catch (e) {
        console.warn("[mic] failed:", e);
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
    updateRms(0);
}

function onMicFrame(frame) {
    let sum = 0;
    for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
    const rms = Math.sqrt(sum / frame.length);
    updateRms(rms);

    const isSpeech = rms > STATE.rmsThreshold;

    // ── Barge-in: speaking during TTS playback stops ECHO mid-sentence.
    // Browser's getUserMedia echoCancellation:true should suppress most
    // self-loop from speakers; we additionally use a higher threshold
    // (1.6x) and a debounce so a brief mic spike doesn't kill the audio.
    if (STATE.ttsActive && isSpeech && rms > STATE.rmsThreshold * 1.6
        && STATE.bargeInDebounce <= 0) {
        console.log("[barge-in] speech detected during TTS, stopping");
        ttsStopAll();
        if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
            STATE.ws.send(JSON.stringify({type: "stop_tts"}));
        }
        STATE.bargeInDebounce = STATE.BARGE_IN_DEBOUNCE;
    }
    if (STATE.bargeInDebounce > 0) STATE.bargeInDebounce--;

    if (isSpeech) {
        // First speech frame — prepend the rolling pre-roll buffer so
        // whisper sees the consonants we'd otherwise miss.
        if (STATE.speechBuffer.length === 0 && STATE.preRollBuffer.length > 0) {
            STATE.speechBuffer = STATE.preRollBuffer.slice();
            STATE.preRollBuffer = [];
        }
        STATE.speechBuffer.push(frame);
        STATE.silenceFrames = 0;
        bumpInteraction();
    } else if (STATE.speechBuffer.length > 0) {
        STATE.speechBuffer.push(frame);
        STATE.silenceFrames++;
    } else {
        // Idle — maintain rolling pre-roll
        STATE.preRollBuffer.push(frame);
        if (STATE.preRollBuffer.length > STATE.PRE_ROLL_FRAMES) {
            STATE.preRollBuffer.shift();
        }
    }

    const longSilence = STATE.silenceFrames >= STATE.silenceFramesNeeded
                       && STATE.speechBuffer.length >= STATE.minUtteranceFrames;
    const capHit = STATE.speechBuffer.length >= STATE.maxUtteranceFrames;

    if (longSilence || capHit) flushUtterance();
}

function flushUtterance() {
    const chunks = STATE.speechBuffer;
    STATE.speechBuffer = [];
    STATE.silenceFrames = 0;
    if (!chunks.length) return;

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
// TTS playback — sequential queue. Each `response.tts_chunk_b64` (one per
// sentence from the streaming brain) is enqueued; we play in order via
// the `audio.onended` chain so audio is gapless.
// ──────────────────────────────────────────────────────────────────────
function ttsEnqueue(b64) {
    let url;
    try {
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes], {type: "audio/mpeg"});
        url = URL.createObjectURL(blob);
    } catch (e) {
        console.error("[tts] decode failed:", e);
        return;
    }
    STATE.ttsQueue.push(url);
    STATE.ttsActive = true;
    if (!STATE.ttsCurrent) ttsPlayNext();
}

function ttsPlayNext() {
    if (!STATE.ttsQueue.length) {
        STATE.ttsCurrent = null;
        STATE.ttsActive = false;
        return;
    }
    const url = STATE.ttsQueue.shift();
    const audio = new Audio(url);
    audio.onended = () => { URL.revokeObjectURL(url); ttsPlayNext(); };
    audio.onerror = () => { URL.revokeObjectURL(url); ttsPlayNext(); };
    STATE.ttsCurrent = audio;
    audio.play().catch(e => {
        console.warn("[tts] play failed:", e);
        URL.revokeObjectURL(url);
        ttsPlayNext();
    });
}

function ttsStopAll() {
    if (STATE.ttsCurrent) {
        try { STATE.ttsCurrent.pause(); } catch (e) {}
        STATE.ttsCurrent = null;
    }
    while (STATE.ttsQueue.length) {
        URL.revokeObjectURL(STATE.ttsQueue.shift());
    }
    STATE.ttsActive = false;
}

// ──────────────────────────────────────────────────────────────────────
// Input handling
// ──────────────────────────────────────────────────────────────────────
$("input-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const text = $("input").value.trim();
    if (!text) return;
    if (STATE.sleeping) setSleeping(false);
    if (!STATE.ws || STATE.ws.readyState !== WebSocket.OPEN) return;
    STATE.ws.send(JSON.stringify({type: "submit", text}));
    $("input").value = "";
    bumpInteraction();
});

$("mic-btn").addEventListener("click", () => {
    if (STATE.sleeping) { setSleeping(false); return; }
    if (STATE.micPausedForMedia) {
        // User explicitly resuming after media auto-pause
        STATE.micPausedForMedia = false;
        $("sub-status").textContent = "ONLINE";
        startMic().catch(() => {});
        return;
    }
    if (STATE.listening) stopMic();
    else startMic();
});

// ──────────────────────────────────────────────────────────────────────
// Boot
// ──────────────────────────────────────────────────────────────────────
setSleeping(true);   // start in sleep mode
connectWs();
console.log("[echo] web UI booted — globe mounted, ws connecting");
