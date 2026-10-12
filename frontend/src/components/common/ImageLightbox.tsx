import React, { useEffect } from 'react';
import { useAppStore } from '../../store/appStore';

/**
 * 图片放大预览（灯箱）：点击缩略图后全屏查看原图。
 * 点击遮罩或按 Esc 关闭。
 */
export const ImageLightbox: React.FC = () => {
  const src = useAppStore((s) => s.lightboxSrc);
  const close = useAppStore((s) => s.closeLightbox);

  useEffect(() => {
    if (!src) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [src, close]);

  if (!src) return null;

  return (
    <div className="image-lightbox" onClick={close} title="点击空白处关闭">
      <button className="image-lightbox-close" onClick={close} title="关闭">
        ×
      </button>
      <img src={src} alt="预览" onClick={(e) => e.stopPropagation()} />
    </div>
  );
};
