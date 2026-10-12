import React, { useEffect, useState } from 'react';
import { useAppStore } from '../../store/appStore';

export const SettingsDialog: React.FC<{ open: boolean; onClose: () => void }> = ({ open, onClose }) => {
  const config = useAppStore((s) => s.config);
  const updateConfig = useAppStore((s) => s.updateConfig);
  const setMode = useAppStore((s) => s.setMode);
  const setWebSearch = useAppStore((s) => s.setWebSearch);

  const [model, setModel] = useState('');
  const [temperature, setTemperature] = useState('');
  const [maxTokens, setMaxTokens] = useState('');
  const [apiKey, setApiKey] = useState('');

  useEffect(() => {
    if (config) {
      setModel(config.model || '');
      setTemperature(config.temperature != null ? String(config.temperature) : '');
      setMaxTokens(config.max_tokens != null ? String(config.max_tokens) : '');
    }
  }, [config, open]);

  if (!open) return null;

  const save = async () => {
    const patch: Record<string, unknown> = {};
    if (model) patch.model = model;
    if (temperature !== '') patch.temperature = Number(temperature);
    if (maxTokens !== '') patch.max_tokens = Number(maxTokens);
    if (apiKey) patch.api_key = apiKey;
    await updateConfig(patch as any);
    setApiKey('');
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-title">设置</div>

        <label className="field">
          <span>模型</span>
          <input value={model} onChange={(e) => setModel(e.target.value)} placeholder="e.g. deepseek/deepseek-chat" />
        </label>

        <label className="field">
          <span>API Key（{config?.api_key_masked || '未设置'}）</span>
          <input type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} placeholder="留空则不修改" />
        </label>

        <div className="field-row">
          <label className="field">
            <span>温度 temperature</span>
            <input value={temperature} onChange={(e) => setTemperature(e.target.value)} placeholder="0.0 ~ 1.0" />
          </label>
          <label className="field">
            <span>最大 token</span>
            <input value={maxTokens} onChange={(e) => setMaxTokens(e.target.value)} placeholder="如 4096" />
          </label>
        </div>

        <div className="field">
          <span>运行模式</span>
          <div className="segmented">
            <button className={config?.runtime_mode === 'agent' ? 'active' : ''} onClick={() => setMode('agent')}>
              Agent（自动推进/可调用工具）
            </button>
            <button className={config?.runtime_mode === 'chat' ? 'active' : ''} onClick={() => setMode('chat')}>
              Chat（一问一答）
            </button>
          </div>
        </div>

        <div className="field">
          <span>联网搜索</span>
          <label className="switch">
            <input
              type="checkbox"
              checked={!!config?.web_search_enabled}
              onChange={(e) => setWebSearch(e.target.checked)}
            />
            <span>{config?.web_search_enabled ? '已开启' : '已关闭'}</span>
          </label>
        </div>

        <div className="modal-actions">
          <button className="btn" onClick={onClose}>
            取消
          </button>
          <button className="btn primary" onClick={save}>
            保存
          </button>
        </div>
      </div>
    </div>
  );
};
