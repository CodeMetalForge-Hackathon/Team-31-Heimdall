/* HEIMDALL mic tap (AudioWorklet). Copies the mic into 2048-sample chunks and posts each one,
 * with the context frame index of its first sample, to the MessagePort it is given
 * (the other end lives in heimdall-listen-worker.js). The audio thread does nothing else.
 *   node.port.postMessage({port}, [port])
 */
class HeimdallTap extends AudioWorkletProcessor {
  constructor() {
    super();
    this.b = new Float32Array(2048);
    this.n = 0;
    this.f0 = 0;
    this.out = null;
    this.port.onmessage = (e) => { if (e.data && e.data.port) this.out = e.data.port; };
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch && this.out) {
      for (let i = 0; i < ch.length; i++) {
        if (this.n === 0) this.f0 = currentFrame + i;
        this.b[this.n++] = ch[i];
        if (this.n === this.b.length) {
          this.out.postMessage({ x: this.b, f0: this.f0 }, [this.b.buffer]);
          this.b = new Float32Array(2048);
          this.n = 0;
        }
      }
    }
    return true;
  }
}

registerProcessor('heimdall-tap', HeimdallTap);
