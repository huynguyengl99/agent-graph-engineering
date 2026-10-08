import remarkBreaks from 'remark-breaks';
import { defaultRemarkPlugins, Streamdown } from 'streamdown';

// Passing `remarkPlugins` replaces streamdown's own (GFM among them), so they
// are kept and line breaks added: the model writes a label on one line and
// the reply on the next, and without this the two run together.
const remarkPlugins = [...Object.values(defaultRemarkPlugins), remarkBreaks];

/**
 * What the agent wrote, rendered as markdown. Streamdown rather than a plain
 * markdown renderer because a reply arrives a few tokens at a time: an
 * unclosed `**` mid-stream is finished for display instead of flashing as
 * literal asterisks. Its default sanitizing stays on, since this is model
 * output and nothing in it is trusted.
 */
export function Markdown({
  children,
  streaming = false,
}: {
  children: string;
  /** Still arriving, so the last block is treated as unfinished. */
  streaming?: boolean;
}) {
  return (
    <Streamdown
      mode={streaming ? 'streaming' : 'static'}
      isAnimating={streaming}
      remarkPlugins={remarkPlugins}
      controls={{ code: true, table: false, mermaid: false }}
      className="space-y-2 whitespace-normal"
    >
      {children}
    </Streamdown>
  );
}
