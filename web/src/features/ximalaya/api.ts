// API of the 「喜马拉雅版」 tab (backlog item 26)
import { ep, req } from "../../api";

export type XimalayaStyleId = "magazine" | "cinema" | "cards";

export interface XimalayaStyle {
  html: string;
  text: string;
  images: string[];
}

export interface XimalayaView {
  styles: Record<XimalayaStyleId, XimalayaStyle> | null;
  dir: string | null;
  stale: boolean;
  notes: string[];
}

export const ximalayaApi = {
  get: (id: string) => req<XimalayaView>("GET", `${ep(id)}/publish/ximalaya`),
  image: (id: string, name: string, v: string) => `${ep(id)}/publish/ximalaya/${encodeURIComponent(name)}?v=${encodeURIComponent(v)}`,
};
