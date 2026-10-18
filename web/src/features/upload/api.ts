// API of this feature (phase 11: 上传喜马拉雅)
import { ep, req } from "../../api";

export interface UploadView {
  upload_page: string;
  audio: { name: string; bytes: number; exported_at: string | null; stale: boolean } | null;
  pack: { stale: boolean; edited: boolean } | null;
  cover: { bytes: number; px: number; rendered_at: string } | null;
  ready: boolean;
}

export const uploadApi = {
  upload: (id: string) => req<UploadView>("GET", `${ep(id)}/upload`),
  coverUrl: (id: string, stamp: string) => `${ep(id)}/upload/cover.jpg?v=${encodeURIComponent(stamp)}`,
  /** Copy the chosen cover into exports/<ep>/, next to the WAV / MP3. */
  saveCover: (id: string) => req<{ path: string; folder: string; name: string }>("POST", `${ep(id)}/upload/save-cover`),
  wavUrl: (id: string, name: string) => `${ep(id)}/exports/${encodeURIComponent(name)}`,
};
