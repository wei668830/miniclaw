import React from 'react';
import type { WebResultItem } from './webSearch';

/**
 * web_search 结果的「引用链接卡片」展示：标题 / 站点 / 时间 / 链接 / 摘要。
 *
 * 卡片整体为外链（`target="_blank"`）：Electron 下经主进程 `setWindowOpenHandler`
 * 用系统浏览器打开原链接，便于「查看原链接内容」。
 */
export const SearchResults: React.FC<{ items: WebResultItem[]; total?: string }> = ({ items, total }) => {
  if (!items.length) return null;

  return (
    <div className="search-results">
      {total && <div className="search-total">共 {total} 条结果</div>}
      {items.map((r, i) => {
        const body = (
          <>
            <div className="search-card-title">{r.title || '（无标题）'}</div>
            {(r.site || r.publish) && (
              <div className="search-card-meta">
                {r.site && <span className="search-site">{r.site}</span>}
                {r.publish && <span className="search-time">{r.publish}</span>}
              </div>
            )}
            {r.url && <div className="search-url">{r.url}</div>}
            {r.summary && (
              <div className="search-summary" title={r.summary}>
                {r.summary}
              </div>
            )}
          </>
        );
        return r.url ? (
          <a key={i} className="search-card" href={r.url} target="_blank" rel="noreferrer" title="打开原链接">
            {body}
          </a>
        ) : (
          <div key={i} className="search-card">
            {body}
          </div>
        );
      })}
    </div>
  );
};
