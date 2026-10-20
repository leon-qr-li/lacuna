import type { Feature } from "../registry";
import { AlbumPage } from "./AlbumPage";
import "./albums.css";
import { t } from "../../i18n";

export const feature: Feature = {
  pages: [{ path: "album", title: t("专辑"), render: () => <AlbumPage /> }],
};
