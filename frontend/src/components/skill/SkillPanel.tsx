import React, { useState } from 'react';
import { useAppStore } from '../../store/appStore';

export const SkillPanel: React.FC = () => {
  const skills = useAppStore((s) => s.skills);
  const loadedSkills = useAppStore((s) => s.loadedSkills);
  const loadSkills = useAppStore((s) => s.loadSkills);
  const [toast, setToast] = useState('');

  const loadedNames = new Set(loadedSkills.map((s) => s.name));

  const onLoad = async (name: string) => {
    const res = await loadSkills([name]);
    if (res.pending.length) {
      setToast(`技能「${name}」已加载，将在你下一条消息中生效`);
    } else if (res.already_loaded.length) {
      setToast(`技能「${name}」本会话已加载，无需重复`);
    } else {
      setToast(`未找到技能「${name}」`);
    }
    setTimeout(() => setToast(''), 3000);
  };

  return (
    <div className="skill-panel">
      <div className="panel-section">
        <div className="panel-title">本会话已加载技能</div>
        {loadedSkills.length === 0 ? (
          <div className="empty-hint">本会话尚未加载技能</div>
        ) : (
          loadedSkills.map((s) => (
            <div key={s.name} className="skill-item loaded">
              <div className="skill-name">
                {s.name}
                <span className="badge">本会话内不可卸载</span>
              </div>
              <div className="skill-desc">{s.description}</div>
            </div>
          ))
        )}
      </div>

      <div className="panel-section">
        <div className="panel-title">可用技能（{skills.length}）</div>
        {skills.map((s) => {
          const loaded = loadedNames.has(s.name);
          return (
            <div key={s.name} className="skill-item">
              <div className="skill-row">
                <div className="skill-name">{s.name}</div>
                <button className="btn small" disabled={loaded} onClick={() => onLoad(s.name)}>
                  {loaded ? '已加载' : '加载'}
                </button>
              </div>
              <div className="skill-desc">{s.description}</div>
            </div>
          );
        })}
        {skills.length === 0 && <div className="empty-hint">未发现技能</div>}
        <div className="panel-hint">
          技能通过「用户对话」加载（加载后不可卸载，如需重置请新建会话）。
        </div>
      </div>

      {toast && <div className="toast">{toast}</div>}
    </div>
  );
};
