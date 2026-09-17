use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use serde_json::{json, Value};
use std::{
    io::{BufRead, BufReader, BufWriter, Write},
    path::PathBuf,
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{atomic::{AtomicU64, Ordering}, Arc, Mutex},
    time::Duration,
};
use tauri::{
    menu::{Menu, MenuItem},
    plugin::PermissionState,
    tray::TrayIconBuilder,
    AppHandle, Manager, State, WindowEvent,
};
use tauri_plugin_notification::NotificationExt;

const CREDENTIAL_SERVICE: &str = "Qingwu";
const CREDENTIAL_USER: &str = "openai-api-key";

struct SidecarClient {
    _child: Child,
    input: BufWriter<ChildStdin>,
    output: BufReader<ChildStdout>,
}

impl SidecarClient {
    fn start(app: &AppHandle) -> Result<Self, String> {
        let current_dir = std::env::current_exe().map_err(|error| error.to_string())?
            .parent().map(PathBuf::from).ok_or("无法定位轻务程序目录")?;
        let adjacent = current_dir.join("qingwu-sidecar.exe");
        let resource = app.path().resource_dir().map_err(|error| error.to_string())?.join("qingwu-sidecar.exe");
        let mut command = if adjacent.is_file() || resource.is_file() {
            Command::new(if adjacent.is_file() { adjacent } else { resource })
        } else {
            let project = PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent()
                .map(PathBuf::from).ok_or("无法定位开发目录")?;
            let mut dev = Command::new("python");
            dev.arg("-m").arg("qingwu_core.sidecar").env("PYTHONPATH", project.join("python"));
            dev
        };
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            command.creation_flags(0x08000000);
        }
        let mut child = command.stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null())
            .spawn().map_err(|error| format!("无法启动轻务核心：{error}"))?;
        let input = child.stdin.take().ok_or("无法连接轻务核心输入")?;
        let output = child.stdout.take().ok_or("无法连接轻务核心输出")?;
        Ok(Self { _child: child, input: BufWriter::new(input), output: BufReader::new(output) })
    }

    fn call(&mut self, request_id: u64, method: &str, params: Value) -> Result<Value, String> {
        let line = serde_json::to_string(&json!({ "id": request_id, "method": method, "params": params }))
            .map_err(|error| error.to_string())?;
        self.input.write_all(line.as_bytes()).and_then(|_| self.input.write_all(b"\n"))
            .and_then(|_| self.input.flush()).map_err(|error| format!("轻务核心连接写入失败：{error}"))?;
        let mut response_line = String::new();
        self.output.read_line(&mut response_line).map_err(|error| format!("轻务核心连接读取失败：{error}"))?;
        if response_line.is_empty() { return Err("轻务核心意外退出".into()); }
        let response: Value = serde_json::from_str(&response_line).map_err(|_| "轻务核心返回了无效响应")?;
        if response.get("ok").and_then(Value::as_bool) == Some(true) {
            Ok(response.get("result").cloned().unwrap_or(Value::Null))
        } else {
            Err(response.pointer("/error/message").and_then(Value::as_str).unwrap_or("轻务核心调用失败").to_string())
        }
    }
}

#[derive(Clone)]
struct SidecarState {
    client: Arc<Mutex<SidecarClient>>,
    next_id: Arc<AtomicU64>,
}

impl SidecarState {
    fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        let request_id = self.next_id.fetch_add(1, Ordering::Relaxed);
        self.client.lock().map_err(|_| "轻务核心连接锁定失败".to_string())?.call(request_id, method, params)
    }
}

fn credential() -> Result<keyring::Entry, String> {
    keyring::Entry::new(CREDENTIAL_SERVICE, CREDENTIAL_USER).map_err(|error| format!("无法访问 Windows Credential Manager：{error}"))
}

#[tauri::command]
fn rpc(method: String, mut params: Value, state: State<'_, SidecarState>) -> Result<Value, String> {
    let use_saved_key = params.as_object_mut().and_then(|value| value.remove("use_saved_api_key"))
        .and_then(|value| value.as_bool()).unwrap_or(false);
    let needs_key = use_saved_key && (method == "fact.extract" || method == "style.generate_card"
        || (method == "draft.generate" && params.get("use_ai").and_then(Value::as_bool) == Some(true)));
    if needs_key {
        let api_key = credential()?.get_password().map_err(|_| "尚未在设置中保存 OpenAI API Key".to_string())?;
        if let Some(object) = params.as_object_mut() { object.insert("api_key".into(), Value::String(api_key)); }
    }
    state.call(&method, params)
}

#[tauri::command]
fn save_api_key(api_key: String) -> Result<(), String> {
    if api_key.trim().is_empty() { return Err("API Key 不能为空".into()); }
    credential()?.set_password(api_key.trim()).map_err(|error| format!("保存 API Key 失败：{error}"))
}

#[tauri::command]
fn has_api_key() -> bool {
    credential().and_then(|entry| entry.get_password().map_err(|error| error.to_string())).is_ok()
}

#[tauri::command]
fn delete_api_key() -> Result<(), String> {
    match credential()?.delete_credential() {
        Ok(()) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()),
        Err(error) => Err(format!("删除 API Key 失败：{error}")),
    }
}

#[tauri::command]
fn list_folder_files(path: String) -> Result<Vec<String>, String> {
    let root = PathBuf::from(path).canonicalize().map_err(|error| format!("无法读取文件夹：{error}"))?;
    if !root.is_dir() {
        return Err("所选路径不是文件夹".into());
    }
    let mut pending = vec![root];
    let mut files = Vec::new();
    while let Some(directory) = pending.pop() {
        let entries = std::fs::read_dir(&directory)
            .map_err(|error| format!("无法读取 {}：{error}", directory.display()))?;
        for entry in entries {
            let path = entry.map_err(|error| error.to_string())?.path();
            if path.is_dir() {
                pending.push(path);
            } else if path.is_file() {
                files.push(path.to_string_lossy().to_string());
            }
            if files.len() > 5000 {
                return Err("单次文件夹导入最多支持 5000 个文件".into());
            }
        }
    }
    files.sort();
    Ok(files)
}

#[tauri::command]
fn save_clipboard_image(app: AppHandle, data_base64: String, mime: String) -> Result<String, String> {
    let extension = match mime.as_str() {
        "image/png" => "png",
        "image/jpeg" => "jpg",
        "image/webp" => "webp",
        _ => return Err("只支持 PNG、JPEG 或 WebP 剪贴板图片".into()),
    };
    let bytes = BASE64.decode(data_base64).map_err(|_| "剪贴板图片数据无效".to_string())?;
    if bytes.len() > 25 * 1024 * 1024 {
        return Err("剪贴板图片不能超过 25 MB".into());
    }
    let directory = app.path().app_local_data_dir().map_err(|error| error.to_string())?.join("clipboard");
    std::fs::create_dir_all(&directory).map_err(|error| format!("无法创建剪贴板材料目录：{error}"))?;
    let timestamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map_err(|error| error.to_string())?.as_millis();
    let path = directory.join(format!("clipboard-{timestamp}.{extension}"));
    std::fs::write(&path, bytes).map_err(|error| format!("无法保存剪贴板图片：{error}"))?;
    Ok(path.to_string_lossy().to_string())
}

fn start_reminder_loop(app: AppHandle, sidecar: SidecarState) {
    tauri::async_runtime::spawn(async move {
        tokio::time::sleep(Duration::from_secs(5)).await;
        loop {
            if let Ok(Value::Array(reminders)) = sidecar.call("timeline.due_reminders", json!({})) {
                for reminder in reminders {
                    let affair = reminder.get("affair_title").and_then(Value::as_str).unwrap_or("轻务事务");
                    let task = reminder.get("title").and_then(Value::as_str).unwrap_or("待办即将到期");
                    let due = reminder.get("due_at").and_then(Value::as_str).unwrap_or("");
                    let _ = app.notification().builder().title(format!("轻务 · {affair}"))
                        .body(format!("{task}\n截止时间：{due}")).show();
                }
            }
            tokio::time::sleep(Duration::from_secs(60)).await;
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            app.handle().plugin(tauri_plugin_autostart::init(
                tauri_plugin_autostart::MacosLauncher::LaunchAgent, None,
            ))?;
            if app.notification().permission_state()? == PermissionState::Unknown {
                let _ = app.notification().request_permission()?;
            }
            let sidecar = SidecarState {
                client: Arc::new(Mutex::new(
                    SidecarClient::start(app.handle()).map_err(std::io::Error::other)?,
                )),
                next_id: Arc::new(AtomicU64::new(1)),
            };
            app.manage(sidecar.clone());
            start_reminder_loop(app.handle().clone(), sidecar);
            let show = MenuItem::with_id(app, "show", "打开轻务", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "完全退出（停止提醒）", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &quit])?;
            TrayIconBuilder::new().icon(
                app.default_window_icon().ok_or_else(|| std::io::Error::other("缺少应用图标"))?.clone(),
            )
                .tooltip("轻务 · 本地事务提醒正在运行").menu(&menu).show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => { if let Some(window) = app.get_webview_window("main") { let _ = window.show(); let _ = window.set_focus(); } }
                    "quit" => app.exit(0),
                    _ => {}
                }).build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
                let _ = window.app_handle().notification().builder().title("轻务仍在后台运行")
                    .body("截止提醒会继续工作。若要停止提醒，请从托盘菜单选择“完全退出”。").show();
            }
        })
        .invoke_handler(tauri::generate_handler![
            rpc, save_api_key, has_api_key, delete_api_key, list_folder_files, save_clipboard_image
        ])
        .run(tauri::generate_context!())
        .expect("轻务启动失败");
}
