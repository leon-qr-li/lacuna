import { Fragment, useEffect, useRef, useState } from "react";
import { t } from "../../i18n";
import { BusyLabel } from "../loading/Loading";
import { MenuNav } from "../mobile/MenuNav";
import { navLinks } from "../registry";
import { enterNew } from "../projects/api";
import { spacesApi } from "../spaces/api";
import "./first-show.css";

/** Someone who belongs to no show (they deleted their last one, or were removed from the only one they
 *  shared): every show page would be refused, so the app opens straight on making their first show (Leon
 *  2026-10-28). The new show's 剧集 then asks for its language and hosts, as after ＋ 新节目. */
export function FirstShow() {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);
  const create = async () => {
    setBusy(true);
    setErr(null);
    try {
      await spacesApi.create(name);
      enterNew();
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">LACUNA</strong>
        <span className="grow" />
        {/* only what works without a show: settings (account, sign out) and the theme */}
        <MenuNav>
          {navLinks
            .filter((l) => l.path === "settings" || l.path === "theme")
            .map((l) => (
              <Fragment key={l.path}>{l.render()}</Fragment>
            ))}
        </MenuNav>
      </header>
      <main className="home first-show">
        <form
          className="card first-show-card"
          data-testid="first-show"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim() && !busy) void create();
          }}
        >
          <h1>{t("建你的第一个节目")}</h1>
          <p className="muted">{t("一档播客、一个客户、一个栏目都可以是一个节目。每个节目有自己的剧集、专辑和素材。")}</p>
          <label className="prj-field">
            <span className="prj-label">{t("节目名")}</span>
            <input
              ref={input}
              value={name}
              maxLength={80}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("比如：周末电影院")}
              data-testid="first-show-name"
            />
          </label>
          {err && <p className="error small">{err}</p>}
          <button type="submit" className="btn btn-primary" disabled={!name.trim() || busy} data-testid="first-show-create">
            <BusyLabel busy={busy} label={t("建好节目")} />
          </button>
          <p className="muted small first-show-note">{t("有人邀请你协作的话，打开邀请邮件里的链接就能加入对方的节目。")}</p>
        </form>
      </main>
    </div>
  );
}
