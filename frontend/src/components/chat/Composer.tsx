import React, { useMemo, useRef, useState } from 'react';
import { useAppStore } from '../../store/appStore';
import type { ComposerImage } from '../../store/appStore';
import { SLASH_COMMANDS, useSlashCommands } from '../../hooks/useSlashCommands';

interface PendingImage extends ComposerImage {
  id: string;
}

let imgSeq = 0;

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
}

export const Composer: React.FC = () => {
  const [text, setText] = useState('');
  const [images, setImages] = useState<PendingImage[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  const streaming = useAppStore((s) => s.streaming);
  const sendMessage = useAppStore((s) => s.sendMessage);
  const stopStream = useAppStore((s) => s.stopStream);
  const openLightbox = useAppStore((s) => s.openLightbox);
  const { run } = useSlashCommands();

  const showCommands = text.startsWith('/') && !text.includes(' ') && images.length === 0;
  const matches = useMemo(
    () => SLASH_COMMANDS.filter((c) => c.name.startsWith(text.slice(1).toLowerCase())),
    [text]
  );

  const addFiles = async (files: File[]) => {
    const imgs = files.filter((f) => f.type.startsWith('image/'));
    if (!imgs.length) return;
    const added: PendingImage[] = [];
    for (const f of imgs) {
      try {
        const dataUrl = await fileToDataUrl(f);
        added.push({ id: `img${Date.now()}-${imgSeq++}`, dataUrl, mime: f.type || 'image/png', name: f.name });
      } catch {
        /* 忽略读取失败的文件 */
      }
    }
    if (added.length) setImages((prev) => [...prev, ...added]);
  };

  const onPaste = async (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    const files: File[] = [];
    for (const it of Array.from(items)) {
      if (it.kind === 'file') {
        const f = it.getAsFile();
        if (f && f.type.startsWith('image/')) files.push(f);
      }
    }
    if (files.length) {
      e.preventDefault();
      await addFiles(files);
    }
  };

  const onDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    const files = Array.from(e.dataTransfer?.files || []).filter((f) => f.type.startsWith('image/'));
    if (files.length) await addFiles(files);
  };

  const onPickFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    await addFiles(files);
    e.target.value = '';
  };

  const removeImage = (id: string) => setImages((prev) => prev.filter((i) => i.id !== id));

  const submit = async () => {
    const value = text.trim();
    if ((!value && images.length === 0) || streaming) return;
    // 纯命令（无图片）走斜杠命令
    if (value.startsWith('/') && images.length === 0) {
      setText('');
      await run(value);
      return;
    }
    const imgs = images;
    setText('');
    setImages([]);
    await sendMessage(value, imgs);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <div className="composer" onDrop={onDrop} onDragOver={(e) => e.preventDefault()}>
      {showCommands && matches.length > 0 && (
        <div className="command-popover">
          {matches.map((c) => (
            <div key={c.name} className="command-item" onClick={() => setText(`/${c.name} `)}>
              <span className="command-name">/{c.name}</span>
              <span className="command-summary">{c.summary}</span>
            </div>
          ))}
        </div>
      )}

      {images.length > 0 && (
        <div className="composer-images">
          {images.map((img) => (
            <div key={img.id} className="composer-image">
              <img
                src={img.dataUrl}
                alt={img.name || '图片'}
                title="点击查看大图"
                onClick={() => openLightbox(img.dataUrl)}
              />
              <button
                className="composer-image-remove"
                title="移除"
                onClick={(e) => {
                  e.stopPropagation();
                  removeImage(img.id);
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="composer-main">
        <textarea
          value={text}
          placeholder="输入消息，Enter 发送，Shift+Enter 换行；可粘贴/拖拽图片；以 / 开头可执行命令"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={onPaste}
        />
        <div className="composer-actions">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            multiple
            style={{ display: 'none' }}
            onChange={onPickFiles}
          />
          <button className="btn small" title="选择图片" onClick={() => fileRef.current?.click()} disabled={streaming}>
            🖼 图片
          </button>
          {streaming ? (
            <button className="btn stop" onClick={stopStream}>
              停止
            </button>
          ) : (
            <button className="btn send" onClick={submit} disabled={!text.trim() && images.length === 0}>
              发送
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
