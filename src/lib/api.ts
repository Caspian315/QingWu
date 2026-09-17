import { invoke } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import { mockCall } from "./mock";

declare global {
  interface Window { __TAURI_INTERNALS__?: unknown }
}

export const isDesktop = () => Boolean(window.__TAURI_INTERNALS__);
export const configuredModel = () => localStorage.getItem("qingwu-model-id") || "gpt-5.4-mini";
export const saveConfiguredModel = (model: string) => localStorage.setItem("qingwu-model-id", model.trim() || "gpt-5.4-mini");

export async function call<T>(method: string, params: Record<string, unknown> = {}): Promise<T> {
  if (!isDesktop()) return mockCall<T>(method, params);
  return invoke<T>("rpc", { method, params });
}

export async function chooseMaterialFiles(): Promise<string[]> {
  if (!isDesktop()) throw new Error("浏览器演示模式不能读取本地文件路径，请在轻务桌面版中使用材料导入。");
  const result = await open({ multiple: true, directory: false, title: "选择要加入轻务的材料" });
  if (!result) return [];
  return Array.isArray(result) ? result : [result];
}

export async function chooseMaterialFolder(): Promise<string[]> {
  if (!isDesktop()) throw new Error("浏览器演示模式不能读取本地文件夹，请在轻务桌面版中使用材料导入。");
  const directory = await open({ multiple: false, directory: true, title: "选择要加入轻务的材料文件夹" });
  if (!directory || Array.isArray(directory)) return [];
  return invoke<string[]>("list_folder_files", { path: directory });
}

export async function chooseStyleFiles(): Promise<string[]> {
  if (!isDesktop()) throw new Error("浏览器演示模式不能读取历史文案文件，请直接粘贴文本。");
  const result = await open({
    multiple: true,
    directory: false,
    title: "选择认可的历史文案",
    filters: [{ name: "文案", extensions: ["txt", "md", "docx", "pdf"] }],
  });
  if (!result) return [];
  return Array.isArray(result) ? result : [result];
}

export async function listenForMaterialDrops(handler: (paths: string[]) => void): Promise<() => void> {
  if (!isDesktop()) return () => undefined;
  const { getCurrentWebviewWindow } = await import("@tauri-apps/api/webviewWindow");
  return getCurrentWebviewWindow().onDragDropEvent((event) => {
    if (event.payload.type === "drop") handler(event.payload.paths);
  });
}

export async function pasteClipboardImage(): Promise<string> {
  if (!isDesktop()) throw new Error("浏览器演示模式不保存剪贴板图片，请在轻务桌面版中使用。");
  if (!navigator.clipboard?.read) throw new Error("当前系统不支持读取剪贴板图片。");
  const items = await navigator.clipboard.read();
  for (const item of items) {
    const mime = item.types.find((type) => type.startsWith("image/"));
    if (!mime) continue;
    const blob = await item.getType(mime);
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let binary = "";
    for (let index = 0; index < bytes.length; index += 0x8000) {
      binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
    }
    return invoke<string>("save_clipboard_image", { dataBase64: btoa(binary), mime });
  }
  throw new Error("剪贴板中没有图片。");
}

export async function chooseArchivePath(defaultName: string): Promise<string | null> {
  if (!isDesktop()) return null;
  return save({ title: "导出轻务归档包", defaultPath: `${defaultName}.zip`, filters: [{ name: "ZIP 归档", extensions: ["zip"] }] });
}

export async function saveApiKey(apiKey: string): Promise<void> {
  if (!isDesktop()) throw new Error("为避免浏览器存储泄露，演示模式不保存 API Key。请使用桌面版。");
  await invoke("save_api_key", { apiKey });
}

export async function credentialStatus(): Promise<boolean> {
  return isDesktop() ? invoke<boolean>("has_api_key") : false;
}

export async function deleteApiKey(): Promise<void> {
  if (isDesktop()) await invoke("delete_api_key");
}

export async function autostartStatus(): Promise<boolean> {
  if (!isDesktop()) return false;
  const { isEnabled } = await import("@tauri-apps/plugin-autostart");
  return isEnabled();
}

export async function setAutostart(enabled: boolean): Promise<void> {
  if (!isDesktop()) throw new Error("浏览器演示模式不能设置开机启动。");
  const { enable, disable } = await import("@tauri-apps/plugin-autostart");
  if (enabled) await enable(); else await disable();
}
