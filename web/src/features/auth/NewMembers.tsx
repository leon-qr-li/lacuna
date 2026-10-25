import { useEffect, useState } from "react";
import { req } from "../../api";
import { t } from "../../i18n";
import { confirmDialog } from "../dialog/Dialog";

/** 「新成员需站长批准」 (owner only, routes/new_members.py): on in beta; turned off at public launch. */
export function NewMembersSwitch() {
  const [on, setOn] = useState<boolean | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    req<{ approval: boolean }>("GET", "/api/site/new-members").then((r) => setOn(r.approval), () => setOn(null));
  }, []);
  if (on === null) return null;
  const flip = async () => {
    if (on) {
      const ok = await confirmDialog({
        title: t("关掉「新成员需站长批准」？"),
        message: t("关掉后，节目管理员可以直接邀请没有账号的人，人数只按套餐限制，不再经过你。正式上线时再关。"),
        confirmLabel: t("关掉"),
        danger: true,
      });
      if (!ok) return;
    }
    setErr(null);
    req<{ approval: boolean }>("PUT", "/api/site/new-members", { on: !on }).then(
      (r) => setOn(r.approval),
      (e) => setErr(String((e as Error).message)),
    );
  };
  return (
    <div className="people-switch" data-testid="new-members-switch">
      <label className="check">
        <input type="checkbox" checked={on} onChange={() => void flip()} data-testid="new-members-approval" />
        {t("新成员需站长批准")}
      </label>
      <p className="muted small">
        {on
          ? t("开着（beta）：节目管理员邀请没有账号的人时，会先变成一条「协作者申请」，出现在下面的试用申请里，你批准后才发邀请。")
          : t("已关掉：节目管理员可以直接邀请新人，人数按套餐限制。")}
      </p>
      {err && <p className="error small">{err}</p>}
    </div>
  );
}
