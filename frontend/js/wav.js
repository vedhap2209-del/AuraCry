// Decode ANY browser-playable audio (wav/mp3/m4a/webm/ogg) and re-encode as 16-bit mono WAV so the server never needs ffmpeg.
const decode = (ctx, buf) => new Promise((res, rej) => { const p = ctx.decodeAudioData(buf, res, rej); if (p && p.catch) p.catch(rej); });
export async function toWav(blob) {
  const Ctx = window.AudioContext || window.webkitAudioContext, ctx = new Ctx();
  try {
    const ab = await decode(ctx, await blob.arrayBuffer());
    const n = ab.length, mono = new Float32Array(n);
    for (let c = 0; c < ab.numberOfChannels; c++) { const ch = ab.getChannelData(c); for (let i = 0; i < n; i++) mono[i] += ch[i] / ab.numberOfChannels; }
    return encode(mono, ab.sampleRate);
  } finally { ctx.close(); }
}
function encode(s, sr) {
  const b = new ArrayBuffer(44 + s.length * 2), v = new DataView(b);
  const str = (o, t) => [...t].forEach((c, i) => v.setUint8(o + i, c.charCodeAt(0)));
  str(0, "RIFF"); v.setUint32(4, 36 + s.length * 2, true); str(8, "WAVE"); str(12, "fmt "); v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); v.setUint16(22, 1, true); v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true); str(36, "data"); v.setUint32(40, s.length * 2, true);
  let o = 44; for (let i = 0; i < s.length; i++, o += 2) { const x = Math.max(-1, Math.min(1, s[i])); v.setInt16(o, x < 0 ? x * 0x8000 : x * 0x7fff, true); }
  return new Blob([v], { type: "audio/wav" });
}
