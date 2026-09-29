/**
 * A WebSocket stand-in so the tests drive open/message/close by hand.
 *
 * chanx-js takes a `socketFactory`, so nothing global is monkey-patched and the
 * real client code (framing, routing, reconnect) runs unchanged.
 */

export class FakeSocket {
  static instances: FakeSocket[] = [];

  readyState = 0;
  sent: Array<Record<string, unknown>> = [];

  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: { code?: number; reason?: string }) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  constructor(readonly url: string) {
    FakeSocket.instances.push(this);
  }

  /** Drop every socket so the next test's client opens a fresh one.
   *
   * The hub is one connection for the whole app, so a client that is still
   * holding an open socket will reuse it and the next test sees none created.
   */
  static closeAll(): void {
    for (const socket of FakeSocket.instances) {
      socket.readyState = 3;
      socket.onclose?.({ code: 1000, reason: 'test teardown' });
    }
  }

  static reset(): void {
    FakeSocket.instances = [];
  }

  static get last(): FakeSocket {
    const socket = FakeSocket.instances.at(-1);
    if (!socket) throw new Error('No socket was created');
    return socket;
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data) as Record<string, unknown>);
  }

  close(code?: number, reason?: string): void {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code, reason });
  }

  /** Complete the handshake. */
  /** Accept, then answer the topic subscribe the client sends on open. */
  acceptAndSubscribe(): void {
    this.accept();
    this.confirmSubscribe();
  }

  /** Answer the topic subscribe the client sent, as the server would. */
  confirmSubscribe(): void {
    const request = this.sent.find((f) => f.action === 'subscribe');
    if (!request) throw new Error('client sent no subscribe frame');
    this.receive({
      action: 'subscribed',
      topic: request.topic,
      ref: request.ref,
    });
  }

  accept(): void {
    this.readyState = 1;
    this.onopen?.({});
  }

  /** Deliver a server frame. */
  receive(frame: object): void {
    this.onmessage?.({ data: JSON.stringify(frame) });
  }

  get lastSent(): Record<string, unknown> {
    const frame = this.sent.at(-1);
    if (!frame) throw new Error('Nothing was sent');
    return frame;
  }
}

export const fakeSocketFactory = (url: string) => new FakeSocket(url);
