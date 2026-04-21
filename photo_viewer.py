import os
import shutil
import tkinter as tk
from tkinter import messagebox, colorchooser
from PIL import Image, ImageTk, ImageOps
import sys
import subprocess
if sys.platform == 'win32':
    import winsound
    import win32clipboard
import json
import io
import threading
import rawpy

class ImageViewer:
    def __init__(self, root):
        self.root = root
        self.root.title("🐦 Water-redstart: the chirping viewer v2.6 (双平台)")
        # 初始窗口大小
        self.root.geometry("900x700")

        # 增加可配置的 UI 颜色和大小属性 (更清新的鸟类主题色)
        self.window_bg_color = "#E8F5E9" # 极其淡的森林绿
        self.ui_bg_color = "#B2EBF2" # 清爽的天蓝色
        self.ui_font_size = 10
        
        # 设置可爱的窗口背景色
        self.root.configure(bg=self.window_bg_color)

        self.is_fullscreen = False
        self.keep_top_bar_in_fullscreen = False

        # 获取当前文件夹下所有图片（屏蔽子目录）
        self.supported_formats = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp', '.arw', '.sr2', '.srf', '.crw', '.cr2', '.cr3', '.nef', '.nrw', '.dng', '.orf', '.rw2', '.raf', '.pef')
        self.current_dir = os.getcwd()
        self.images = [
            f for f in os.listdir(self.current_dir)
            if os.path.isfile(os.path.join(self.current_dir, f)) and f.lower().endswith(self.supported_formats)
        ]
        self.images.sort()

        self.index = 0
        self.select_folder_name = "SELECT"
        self.history = []  # 记录操作历史用于撤销
        
        # 图片预加载缓存
        self.image_cache = {}
        self.preload_thread = None
        
        # 尝试读取上一次的进度配置
        self.config_file = os.path.join(self.current_dir, ".birdviewer_config.json")
        self.image_quality = tk.IntVar(value=8000)
        self.load_config()
        
        # 添加一个顶部控制面板背景 (缩小高度)
        self.top_frame = tk.Frame(self.root, bg=self.ui_bg_color)
        self.top_frame.pack(fill=tk.X)
        self.top_info_label = tk.Label(self.top_frame, text="✨ 准备好寻找最可爱的小鸟了吗？ ✨", font=("Microsoft YaHei", self.ui_font_size), fg="#555555", bg=self.ui_bg_color)
        self.top_info_label.pack(pady=2)
        
        # 进度条
        self.progress_scale = tk.Scale(self.top_frame, from_=0, to=len(self.images)-1 if self.images else 0, orient=tk.HORIZONTAL, bg=self.ui_bg_color, highlightthickness=0, showvalue=0, command=self.on_progress_change)
        self.progress_scale.pack(fill=tk.X, padx=20, pady=1)

        # 使用 Canvas 来显示图片并支持放大拖拽
        # 设置内边距和圆角边框感 (缩减内边距提高图片占比)
        self.img_frame = tk.Frame(self.root, bg=self.window_bg_color, bd=0)
        self.img_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(self.img_frame, bg='#FFFFFF', relief=tk.GROOVE, bd=2)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_mouse_drag)

        # 视图控制变量
        self.is_fit = True
        self.current_scale = 1.0
        self.im_x = 0
        self.im_y = 0
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.reverse_mode = False

        # 热键配置
        self.hotkey_next = 'd'
        self.hotkey_copy = 'w'
        self.hotkey_undo = 'a'
        self.hotkey_clip = 's'
        self.hotkey_arrow_left = 'Left'
        self.hotkey_arrow_right = 'Right'
        self.hotkey_arrow_up = 'Up'
        self.hotkey_arrow_down = 'Down'
        
        self._current_bind_next = None
        self._current_bind_copy = None
        self._current_bind_undo = None
        self._current_bind_clip = None
        self._current_bind_arrow_left = None
        self._current_bind_arrow_right = None
        self._current_bind_arrow_up = None
        self._current_bind_arrow_down = None

        self.create_menu()
        self.apply_bindings()

        # 绑定固定快捷键
        self.root.bind("<F11>", self.toggle_fullscreen)
        self.root.bind("<Escape>", self.exit_fullscreen)
        
        # 监听画板尺寸变化，防抖刷新
        self.canvas.bind("<Configure>", self.on_resize)

        self.current_img_obj = None  # 原始图片对象
        self.tk_image = None         # tkinter可用的图片对象缓存(防止被垃圾回收)
        self._resize_job = None      # 延迟重绘的任务标识

        # 延迟100ms加载第一张图片，等待窗口初始化完成
        self.root.after(100, self.load_image)
        # 延迟200ms切换为英文输入法，防止中文输入法吞掉快捷键
        self.root.after(200, self.switch_to_english_ime)

    def switch_to_english_ime(self):
        if sys.platform == 'win32':
            try:
                import ctypes
                # 获取 tkinter 真实窗口句柄而不是系统前台窗口
                hwnd = self.root.winfo_id()
                # 加载美式英语键盘布局 (00000409)
                hkl = ctypes.windll.user32.LoadKeyboardLayoutW("00000409", 1)
                # 取消 IME 的关联，防止中文输入法拦截按键
                ctypes.windll.imm32.ImmAssociateContext(hwnd, 0)
                # 发送切换输入法消息
                ctypes.windll.user32.SendMessageW(hwnd, 0x0050, 0, hkl)
            except Exception as e:
                print(f"切换输入法失败: {e}")

    def open_folder(self):
        from tkinter import filedialog
        folder_selected = filedialog.askdirectory(title="选择包含照片的文件夹")
        if folder_selected:
            # 清理当前资源
            self.current_img_obj = None
            self.tk_image = None
            self.images = []
            self.image_cache = {}
            if self.canvas and hasattr(self, 'image_on_canvas') and self.image_on_canvas:
                self.canvas.delete(self.image_on_canvas)
                
            self.current_dir = folder_selected
            self.config_file = os.path.join(self.current_dir, ".birdviewer_config.json")
            
            # 重新获取图片
            self.images = [
                f for f in os.listdir(self.current_dir)
                if os.path.isfile(os.path.join(self.current_dir, f)) and f.lower().endswith(self.supported_formats)
            ]
            self.images.sort()
            
            self.index = 0
            self.history = []
            
            # 读取上一次的进度配置
            self.load_config()
            
            if self.images:
                self.progress_scale.config(to=len(self.images)-1)
                self.progress_scale.set(self.index)
            else:
                self.progress_scale.config(to=0)
                self.progress_scale.set(0)
                self.top_info_label.config(text="📂 当前文件夹没有找到支持的照片...")
                
            if self.reverse_var.get():
                self.images.reverse()
                self.index = len(self.images) - 1 - self.index
                self.progress_scale.set(self.index)
                
            self.update_title()
            self.load_image()

    def create_menu(self):
        self.menubar = tk.Menu(self.root)
        
        # 文件菜单
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="打开照片文件夹...", command=self.open_folder)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)
        self.menubar.add_cascade(label="文件", menu=file_menu)
        
        # 设置菜单
        settings_menu = tk.Menu(self.menubar, tearoff=0)
        
        self.reverse_var = tk.BooleanVar(value=False)
        settings_menu.add_checkbutton(label="倒序选片 (从后往前)", variable=self.reverse_var, command=self.toggle_reverse)
        
        self.low_memory_mode = tk.BooleanVar(value=False)
        settings_menu.add_checkbutton(label="省内存模式 (预加载20张)", variable=self.low_memory_mode)
        
        quality_menu = tk.Menu(settings_menu, tearoff=0)
        quality_menu.add_radiobutton(label="2K (运行快，省内存)", variable=self.image_quality, value=2000, command=self.change_quality)
        quality_menu.add_radiobutton(label="4K (平衡)", variable=self.image_quality, value=4000, command=self.change_quality)
        quality_menu.add_radiobutton(label="8K (默认，最高清)", variable=self.image_quality, value=8000, command=self.change_quality)
        settings_menu.add_cascade(label="照片显示画质", menu=quality_menu)
        
        settings_menu.add_separator()
        
        settings_menu.add_command(label="修改操作热键与文件夹...", command=self.show_hotkey_dialog)
        self.menubar.add_cascade(label="设置", menu=settings_menu)
        
        # 帮助菜单
        help_menu = tk.Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="操作说明", command=lambda: messagebox.showinfo(
            "操作说明", 
            f"- 按 下一张 ({self.hotkey_next.upper()}): 翻到下一张图片\n"
            f"- 按 挑出 ({self.hotkey_copy.upper()}): 复制本图片至{self.select_folder_name}文件夹并翻页\n"
            f"- 按 撤销 ({self.hotkey_undo.upper()}): 撤销上一步操作并退回\n"
            f"- 按 复制 ({self.hotkey_clip.upper()}): 将当前照片复制到系统剪贴板\n"
            "- F11: 切换全屏\n"
            "- Esc: 退出全屏"
        ))
        help_menu.add_separator()
        help_menu.add_command(label="关于", command=lambda: messagebox.showinfo(
            "关于", "🐦 Water-redstart: the chirping viewer\n\n版本：2.6 (双平台)\n作者：Crowpaw@2026\n鸣谢：ARC, Untribiium, ~ris, 蓝嘴红鹊, 欧鹭风云, 瑞瑞的, 白鹡鸰, 灰喜鹊, 碳酸, Gemini 3.1 Pro\n于一"
        ))
        self.menubar.add_cascade(label="帮助", menu=help_menu)
        
        self.root.config(menu=self.menubar)

    def apply_bindings(self):
        # 解绑旧的热键
        for attr in ['_current_bind_next', '_current_bind_copy', '_current_bind_undo', '_current_bind_clip',
                     '_current_bind_arrow_left', '_current_bind_arrow_right', '_current_bind_arrow_up', '_current_bind_arrow_down']:
            old_sym = getattr(self, attr, None)
            if old_sym:
                try:
                    self.root.unbind(f"<{old_sym}>")
                except tk.TclError:
                    pass
            
        # 绑定新的热键
        self.root.bind(f"<{self.hotkey_next}>", self.next_image)
        self.root.bind(f"<{self.hotkey_copy}>", self.copy_and_next)
        self.root.bind(f"<{self.hotkey_undo}>", self.undo_action)
        self.root.bind(f"<{self.hotkey_clip}>", self.copy_to_os_clipboard)
        
        self.root.bind(f"<{self.hotkey_arrow_left}>", self.prev_image)
        self.root.bind(f"<{self.hotkey_arrow_right}>", self.next_image)
        self.root.bind(f"<{self.hotkey_arrow_up}>", self.copy_and_next)
        self.root.bind(f"<{self.hotkey_arrow_down}>", self.copy_to_os_clipboard)
        
        self._current_bind_next = self.hotkey_next
        self._current_bind_copy = self.hotkey_copy
        self._current_bind_undo = self.hotkey_undo
        self._current_bind_clip = self.hotkey_clip
        self._current_bind_arrow_left = self.hotkey_arrow_left
        self._current_bind_arrow_right = self.hotkey_arrow_right
        self._current_bind_arrow_up = self.hotkey_arrow_up
        self._current_bind_arrow_down = self.hotkey_arrow_down

        self.update_title()

    def toggle_reverse(self):
        self.reverse_mode = self.reverse_var.get()
        self.images.reverse()
        self.index = len(self.images) - 1 - self.index
        # history reset may be good, or just update indices in history, but simpler to clear history
        self.history.clear()
        self.progress_scale.set(self.index)
        self.load_image()

    def change_quality(self):
        self.image_cache.clear()
        self.save_config()
        self.load_image()

    def get_select_count(self):
        select_folder_path = self.select_folder_name if os.path.isabs(self.select_folder_name) else os.path.join(self.current_dir, self.select_folder_name)
        if not os.path.exists(select_folder_path):
            return 0
        try:
            return sum(1 for f in os.listdir(select_folder_path) 
                       if os.path.isfile(os.path.join(select_folder_path, f)) and f.lower().endswith(self.supported_formats))
        except:
            return 0

    def update_title(self):
        select_count = self.get_select_count()
        if self.images and self.index < len(self.images):
            img_name = self.images[self.index]
            self.root.title(f"🐦 Water-redstart: the chirping viewer v2.6 | 进度: {self.index + 1}/{len(self.images)} | 📁已选: {select_count} | 当前: {img_name}")
            self.top_info_label.config(
                text=f"🐾 进度：{self.index + 1} / {len(self.images)} 📷 【{img_name}】 | 🌲 已挑出: {select_count}只 | 🕊️ 跳过: '{self.hotkey_next.upper()}'  💖 挑出: '{self.hotkey_copy.upper()}'  ⏪ 撤销: '{self.hotkey_undo.upper()}'  📋 剪贴: '{self.hotkey_clip.upper()}'"
            )
        else:
            self.root.title(f"🐦 Water-redstart: the chirping viewer v2.6")
            self.top_info_label.config(text=f"🌲 已挑出: {select_count}只 | 🕊️ 跳过: '{self.hotkey_next.upper()}' | 💖 挑出: '{self.hotkey_copy.upper()}' | ⏪ 撤销: '{self.hotkey_undo.upper()}' | 📋 剪贴: '{self.hotkey_clip.upper()}'")

    def show_hotkey_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("🎈 自定义魔法设置 🎈")
        dialog.geometry("450x620")
        dialog.configure(bg="#FFECD2")
        dialog.transient(self.root)  # 置于主窗口之上
        dialog.grab_set()  # 模态对话框
        
        # 居中标题
        tk.Label(dialog, text="💫 设定你的专属偏好 💫", bg="#FFECD2", fg="#d63384", font=("Microsoft YaHei", 12, "bold")).grid(row=0, column=0, columnspan=2, pady=10)
        
        dialog.temp_next = self.hotkey_next
        dialog.temp_copy = self.hotkey_copy
        dialog.temp_undo = self.hotkey_undo
        dialog.temp_clip = self.hotkey_clip
        dialog.temp_arrow_left = getattr(self, 'hotkey_arrow_left', 'Left')
        dialog.temp_arrow_right = getattr(self, 'hotkey_arrow_right', 'Right')
        dialog.temp_arrow_up = getattr(self, 'hotkey_arrow_up', 'Up')
        dialog.temp_arrow_down = getattr(self, 'hotkey_arrow_down', 'Down')
        dialog.temp_color = self.ui_bg_color
        dialog.temp_keep_top_bar = tk.BooleanVar(value=self.keep_top_bar_in_fullscreen)

        def prompt_key(btn, attr_name):
            prompt = tk.Toplevel(dialog)
            prompt.title("录入按键")
            prompt.geometry("250x120")
            prompt.transient(dialog)
            prompt.grab_set()
            prompt.configure(bg="#FFECD2")
            tk.Label(prompt, text="请按下你想要设置的按键\n\n(支持方向键、回车、字母等)", bg="#FFECD2", font=("Microsoft YaHei", 10)).pack(expand=True)
            def on_key(event):
                sym = event.keysym
                setattr(dialog, attr_name, sym)
                btn.config(text=f"[{sym}] (点击修改)")
                prompt.destroy()
            prompt.bind("<Key>", on_key)
            prompt.focus_set()

        tk.Label(dialog, text="👉 下一张快捷键:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=1, column=0, padx=20, pady=5, sticky="e")
        btn_next = tk.Button(dialog, text=f"[{self.hotkey_next}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_next, 'temp_next'))
        btn_next.grid(row=1, column=1, sticky="w")
        
        tk.Label(dialog, text="💖 挑出快捷键:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=2, column=0, padx=20, pady=5, sticky="e")
        btn_copy = tk.Button(dialog, text=f"[{self.hotkey_copy}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_copy, 'temp_copy'))
        btn_copy.grid(row=2, column=1, sticky="w")

        tk.Label(dialog, text="⏪ 撤销快捷键:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=3, column=0, padx=20, pady=5, sticky="e")
        btn_undo = tk.Button(dialog, text=f"[{self.hotkey_undo}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_undo, 'temp_undo'))
        btn_undo.grid(row=3, column=1, sticky="w")
        
        tk.Label(dialog, text="� 复制快捷键:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=4, column=0, padx=20, pady=5, sticky="e")
        btn_clip = tk.Button(dialog, text=f"[{self.hotkey_clip}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_clip, 'temp_clip'))
        btn_clip.grid(row=4, column=1, sticky="w")
        
        tk.Label(dialog, text="⬅️ 返回上张键:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=5, column=0, padx=20, pady=5, sticky="e")
        btn_arrow_left = tk.Button(dialog, text=f"[{getattr(self, 'hotkey_arrow_left', 'Left')}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_arrow_left, 'temp_arrow_left'))
        btn_arrow_left.grid(row=5, column=1, sticky="w")

        tk.Label(dialog, text="➡️ 快进下张键:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=6, column=0, padx=20, pady=5, sticky="e")
        btn_arrow_right = tk.Button(dialog, text=f"[{getattr(self, 'hotkey_arrow_right', 'Right')}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_arrow_right, 'temp_arrow_right'))
        btn_arrow_right.grid(row=6, column=1, sticky="w")

        tk.Label(dialog, text="⬆️ 挑出热键2:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=7, column=0, padx=20, pady=5, sticky="e")
        btn_arrow_up = tk.Button(dialog, text=f"[{getattr(self, 'hotkey_arrow_up', 'Up')}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_arrow_up, 'temp_arrow_up'))
        btn_arrow_up.grid(row=7, column=1, sticky="w")

        tk.Label(dialog, text="⬇️ 剪贴板热键2:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=8, column=0, padx=20, pady=5, sticky="e")
        btn_arrow_down = tk.Button(dialog, text=f"[{getattr(self, 'hotkey_arrow_down', 'Down')}] (点击修改)", width=18, bg="#FFFFFF", command=lambda: prompt_key(btn_arrow_down, 'temp_arrow_down'))
        btn_arrow_down.grid(row=8, column=1, sticky="w")

        tk.Label(dialog, text="📁 挑出文件夹名:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=9, column=0, padx=20, pady=5, sticky="e")
        
        folder_frame = tk.Frame(dialog, bg="#FFECD2")
        folder_frame.grid(row=9, column=1, sticky="w")
        
        entry_folder = tk.Entry(folder_frame, width=15, font=("Arial", 11), justify="center", bd=2, relief=tk.SUNKEN)
        entry_folder.insert(0, self.select_folder_name)
        entry_folder.pack(side=tk.LEFT, padx=(0, 5))
        
        def browse_folder():
            from tkinter import filedialog
            selected = filedialog.askdirectory(title="选择一个文件夹作为挑出目录", parent=dialog)
            if selected:
                entry_folder.delete(0, tk.END)
                entry_folder.insert(0, selected)
                
        btn_browse = tk.Button(folder_frame, text="浏览...", bg="#FFFFFF", command=browse_folder)
        btn_browse.pack(side=tk.LEFT)

        def choose_color():
            c = colorchooser.askcolor(title="选择顶部UI背景颜色", initialcolor=self.ui_bg_color)
            if c[1]:
                dialog.temp_color = c[1]
                btn_color.config(bg=c[1])

        tk.Label(dialog, text="🎨 顶部横幅颜色:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=10, column=0, padx=20, pady=5, sticky="e")
        btn_color = tk.Button(dialog, text=" 选择颜色 ", width=18, bg=self.ui_bg_color, command=choose_color)
        btn_color.grid(row=10, column=1, sticky="w")

        tk.Label(dialog, text="🔠 顶部文字大小:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=11, column=0, padx=20, pady=5, sticky="e")
        scale_size = tk.Scale(dialog, from_=6, to=24, orient=tk.HORIZONTAL, bg="#FFECD2", highlightthickness=0, length=140)
        scale_size.set(self.ui_font_size)
        scale_size.grid(row=11, column=1, sticky="w")
        
        tk.Label(dialog, text="📺 全屏选项:", bg="#FFECD2", font=("Microsoft YaHei", 10)).grid(row=12, column=0, padx=20, pady=5, sticky="e")
        chk_top_bar = tk.Checkbutton(dialog, text="全屏时保留上方菜单栏", variable=dialog.temp_keep_top_bar, bg="#FFECD2", font=("Microsoft YaHei", 10))
        chk_top_bar.grid(row=12, column=1, sticky="w")
        
        def save():
            new_folder = entry_folder.get().strip()
            
            if not new_folder:
                messagebox.showwarning("哎呀", "文件夹名不能为空哦！", parent=dialog)
                return
            if len(set([dialog.temp_next, dialog.temp_copy, dialog.temp_undo, dialog.temp_clip])) < 4:
                messagebox.showwarning("哎呀", "不同功能的热键不能重复！", parent=dialog)
                return
            if len(set([dialog.temp_arrow_left, dialog.temp_arrow_right, dialog.temp_arrow_up, dialog.temp_arrow_down])) < 4:
                messagebox.showwarning("哎呀", "方向动作热键不能互相重复！", parent=dialog)
                return
                
            self.hotkey_next = dialog.temp_next
            self.hotkey_copy = dialog.temp_copy
            self.hotkey_undo = dialog.temp_undo
            self.hotkey_clip = dialog.temp_clip
            self.hotkey_arrow_left = dialog.temp_arrow_left
            self.hotkey_arrow_right = dialog.temp_arrow_right
            self.hotkey_arrow_up = dialog.temp_arrow_up
            self.hotkey_arrow_down = dialog.temp_arrow_down
            self.select_folder_name = new_folder
            self.keep_top_bar_in_fullscreen = dialog.temp_keep_top_bar.get()
            
            # Update UI Style
            self.ui_bg_color = dialog.temp_color
            self.ui_font_size = scale_size.get()
            self.top_frame.config(bg=self.ui_bg_color)
            self.top_info_label.config(bg=self.ui_bg_color, font=("Microsoft YaHei", self.ui_font_size))
            
            # 重新生成菜单（更新帮助说明里的热键显示）
            self.create_menu()
            self.apply_bindings()
            
            # Apply fullscreen changes if currently in fullscreen
            if self.is_fullscreen:
                if not self.keep_top_bar_in_fullscreen:
                    self.root.config(menu="")
                    self.top_frame.pack_forget()
                else:
                    self.root.config(menu=self.menubar)
                    self.top_frame.pack(fill=tk.X, before=self.img_frame)

            self.save_config()
            messagebox.showinfo("成功啦", "小魔法重新生效啦！✨", parent=dialog)
            dialog.destroy()
            
        btn_save = tk.Button(dialog, text="🎀 保存设置", command=save, width=20, font=("Microsoft YaHei", 11, "bold"), bg="#FFB6C1", fg="white", activebackground="#FF69B4", bd=0, cursor="hand2")
        btn_save.grid(row=13, column=0, columnspan=2, pady=20)

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    last_img = config.get("last_image")
                    if last_img and last_img in self.images:
                        self.index = self.images.index(last_img)
                    self.keep_top_bar_in_fullscreen = config.get("keep_top_bar_in_fullscreen", False)
                    self.image_quality.set(config.get("image_quality", 8000))
                    self.select_folder_name = config.get("select_folder_name", "SELECT")
            except Exception:
                pass

    def save_config(self):
        if self.images and self.index < len(self.images):
            try:
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        "last_image": self.images[self.index],
                        "keep_top_bar_in_fullscreen": getattr(self, 'keep_top_bar_in_fullscreen', False),
                        "image_quality": self.image_quality.get(),
                        "select_folder_name": self.select_folder_name
                    }, f)
            except Exception:
                pass

    def read_image_fast(self, img_path):
        """支持RAW格式和普通图片的快速读取"""
        ext = os.path.splitext(img_path)[1].lower()
        size_val = getattr(self, 'image_quality', tk.IntVar(value=8000)).get()
        target_size = (size_val, size_val)
        try:
            if ext in ('.arw', '.sr2', '.srf', '.crw', '.cr2', '.cr3', '.nef', '.nrw', '.dng', '.orf', '.rw2', '.raf', '.pef'):
                # 对于RAW照片，使用rawpy提取内嵌的预览图（通常是jpeg格式），速度极快数百倍
                with rawpy.imread(img_path) as raw:
                    try:
                        thumb = raw.extract_thumb()
                    except rawpy.LibRawNoThumbnailError:
                        # 没有缩略图则执行完整的后处理渲染，但对性能极不友好
                        rgb = raw.postprocess(half_size=True, use_camera_wb=True)
                        img = Image.fromarray(rgb)
                        img.thumbnail(target_size, Image.Resampling.LANCZOS)
                        return ImageOps.exif_transpose(img)
                        
                if thumb.format in (rawpy.ThumbFormat.JPEG, rawpy.ThumbFormat.BITMAP):
                    img = Image.open(io.BytesIO(thumb.data))
                    img.draft("RGB", target_size) # 极致加速：利用libjpeg在解码时就降采样
                    img = ImageOps.exif_transpose(img)
                    img.thumbnail(target_size, Image.Resampling.LANCZOS)
                    return img
            
            # 普通照片读取
            img = Image.open(img_path)
            img.draft("RGB", target_size) # 极致加速普通巨型JPG解码
            img = ImageOps.exif_transpose(img)
            img.thumbnail(target_size, Image.Resampling.LANCZOS)
            return img
        except Exception as e:
            print(f"解析图片加速失败 {img_path}: {e}")
            return None

    def preload_images_worker(self, current_idx):
        """后台预加载后续图片，保证极端暴力的盲开连翻也毫无卡顿"""
        to_cache_indices = []
        for i in range(1, 6):
            if current_idx - i >= 0:
                to_cache_indices.append(current_idx - i)
                
        preload_count = 20 if getattr(self, 'low_memory_mode', None) and self.low_memory_mode.get() else 50
        for i in range(1, preload_count + 1):
            if current_idx + i < len(self.images):
                to_cache_indices.append(current_idx + i)

        new_cache = {}
        for idx in to_cache_indices:
            if idx in self.image_cache:
                new_cache[idx] = self.image_cache[idx]

        self.image_cache = new_cache  # 此处切断对其他不要图片的引用让垃圾回收

        for idx in to_cache_indices:
            # 若频繁翻页，打断之前的长时加载循环
            if abs(self.index - current_idx) > 2:
                break
                
            if idx not in self.image_cache:
                img_path = os.path.join(self.current_dir, self.images[idx])
                img_obj = self.read_image_fast(img_path)
                if img_obj:
                    self.image_cache[idx] = img_obj
                        
    def show_end_dialog(self):
        if getattr(self, 'end_dialog_open', False):
            return
        self.end_dialog_open = True
        
        end_window = tk.Toplevel(self.root)
        end_window.title("🎉 挑图完成！")
        end_window.geometry("400x320")
        end_window.configure(bg="#E0F7FA")
        end_window.transient(self.root)
        end_window.grab_set()

        tk.Label(end_window, text="🐣 恭喜！所有照片都已经挑完啦！\n请问您想怎么处理文件呢？", font=("Microsoft YaHei", 12, "bold"), bg="#E0F7FA", fg="#006064", pady=15).pack()

        def do_delete_self():
            try:
                if hasattr(self, 'config_file') and os.path.exists(self.config_file):
                    os.remove(self.config_file)
            except Exception as e:
                print(f"配置文件删除失败: {e}")
                
            exe_path = os.path.abspath(sys.argv[0])
            exe_dir = os.path.dirname(exe_path)
            current_dir_abs = os.path.abspath(self.current_dir) if hasattr(self, 'current_dir') and self.current_dir else ""
            
            if exe_dir != current_dir_abs:
                return
                
            if sys.platform == 'win32':
                bat_path = os.path.join(os.environ.get('TEMP', 'C:\\'), 'del_self.bat')
                exe_path = sys.argv[0]
                with open(bat_path, 'w') as f:
                    f.write(f'@echo off\nping 127.0.0.1 -n 2 > nul\ndel "{exe_path}"\ndel "%~f0"')
                subprocess.Popen(bat_path, shell=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
            else:
                try:
                    os.remove(sys.argv[0])
                except:
                    pass

        def do_delete_originals():
            for img in self.images:
                try:
                    os.remove(os.path.join(self.current_dir, img))
                except:
                    pass

        def on_action(choice):
            if choice == 1:
                do_delete_self()
            elif choice == 2:
                do_delete_originals()
            elif choice == 3:
                do_delete_originals()
                do_delete_self()
            self.end_dialog_open = False
            end_window.destroy()
            self.root.destroy()

        end_window.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, 'end_dialog_open', False), end_window.destroy()))

        btn_style = {"font": ("Microsoft YaHei", 10), "width": 25, "pady": 5, "fg": "white", "bd": 0, "cursor": "hand2"}

        b1 = tk.Button(end_window, text="🐥 1. 删除本看图程序", bg="#4DD0E1", activebackground="#26C6DA", command=lambda: on_action(1))
        b1.config(**btn_style)
        b1.pack(pady=6)

        b2 = tk.Button(end_window, text="🔥 2. 删除本文件夹中原片", bg="#FF8A65", activebackground="#4DD0E1", command=lambda: on_action(2))
        b2.config(**btn_style)
        b2.pack(pady=6)

        b3 = tk.Button(end_window, text="☄️ 3. 两者全部删除", bg="#FF5252", activebackground="#FF1744", command=lambda: on_action(3))
        b3.config(**btn_style)
        b3.pack(pady=6)

        b4 = tk.Button(end_window, text="🌸 4. 啥也不删，单纯退出", bg="#81C784", activebackground="#4DB6AC", command=lambda: on_action(4))
        b4.config(**btn_style)
        b4.pack(pady=6)

    def on_progress_change(self, val):
        new_idx = int(val)
        if new_idx != self.index and 0 <= new_idx < len(self.images):
            self.index = int(new_idx)
            self.load_image()

    def start_preload(self):
        # 抛入后台线程进行加载，不阻塞UI主线程
        if self.preload_thread and self.preload_thread.is_alive():
            return
        self.preload_thread = threading.Thread(target=self.preload_images_worker, args=(self.index,), daemon=True)
        self.preload_thread.start()

    def load_image(self):
        self.save_config()
        # 检查有没有图片
        if not self.images:
            if not getattr(self, 'prompted_for_folder', False):
                self.prompted_for_folder = True
                if messagebox.askyesno("提示", "当前目录为空，没有找到支持的照片！\n是否手动选择一个包含照片的文件夹？"):
                    self.open_folder()
                    return
            messagebox.showinfo("提示", "未找到可显示的照片，即将退出程序哦！")
            self.root.destroy()
            return
            
        self.prompted_for_folder = False

        # 检查是否看到最后一张了
        if self.index >= len(self.images):
            # 将索引先倒退回最后一张，防止越界崩溃
            self.index = len(self.images) - 1
            self.show_end_dialog()
            return

        img_path = os.path.join(self.current_dir, self.images[self.index])
        
        try:
            # 优先从多线程缓存中拿，拿到直接显示
            if self.index in self.image_cache:
                self.current_img_obj = self.image_cache[self.index]
            else:
                raw_img = self.read_image_fast(img_path)
                if not raw_img:
                    raise Exception("解析图片返回为空")
                self.current_img_obj = raw_img

            self.is_fit = True
            self.update_title()
            
            # Update progress bar
            self.progress_scale.set(self.index)
            
            self.display_image()
            
            # 本页渲染完毕后，触发下两张图片的预感加载
            self.start_preload()
            
        except Exception as e:
            print(f"无法打开图片 {img_path}: {e}")
            self.index += 1
            if self.index < len(self.images):
                self.root.after(1, self.load_image)
            else:
                self.index = len(self.images) - 1
                self.show_end_dialog()

    def on_mouse_wheel(self, event):
        if not getattr(self, 'current_img_obj', None): return
        self.is_fit = False
        scale_factor = 1.1 if event.delta > 0 else 0.9
        
        x = event.x
        y = event.y
        ww = self.canvas.winfo_width()
        wh = self.canvas.winfo_height()
        
        cursor_im_x = self.im_x + (x - ww / 2) / self.current_scale
        cursor_im_y = self.im_y + (y - wh / 2) / self.current_scale
        
        self.current_scale *= scale_factor
        
        self.im_x = cursor_im_x - (x - ww / 2) / self.current_scale
        self.im_y = cursor_im_y - (y - wh / 2) / self.current_scale
        
        self.display_image()

    def on_button_press(self, event):
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_mouse_drag(self, event):
        if not getattr(self, 'current_img_obj', None): return
        self.is_fit = False
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y
        self.drag_start_x = event.x
        self.drag_start_y = event.y
        
        self.im_x -= dx / self.current_scale
        self.im_y -= dy / self.current_scale
        
        self.display_image()

    def display_image(self, event=None):
        if not self.current_img_obj:
            return

        ww = self.canvas.winfo_width()
        wh = self.canvas.winfo_height()

        if ww < 10 or wh < 10:
            ww, wh = 800, 600

        img_w, img_h = self.current_img_obj.size

        if self.is_fit:
            self.current_scale = min(ww / img_w, wh / img_h)
            self.im_x = img_w / 2
            self.im_y = img_h / 2

        src_w = max(1, ww / self.current_scale)
        src_h = max(1, wh / self.current_scale)

        left = self.im_x - src_w / 2
        top = self.im_y - src_h / 2
        right = self.im_x + src_w / 2
        bottom = self.im_y + src_h / 2

        crop_left = max(0, left)
        crop_top = max(0, top)
        crop_right = min(img_w, right)
        crop_bottom = min(img_h, bottom)

        if crop_right > crop_left and crop_bottom > crop_top:
            cropped = self.current_img_obj.crop((crop_left, crop_top, crop_right, crop_bottom))
            
            dest_left = max(0, (crop_left - left) * self.current_scale)
            dest_top = max(0, (crop_top - top) * self.current_scale)
            dest_w = max(1, (crop_right - crop_left) * self.current_scale)
            dest_h = max(1, (crop_bottom - crop_top) * self.current_scale)

            # 使用 BILINEAR 加速交互期的拖动与缩放刷新
            resized_img = cropped.resize((int(dest_w), int(dest_h)), Image.Resampling.BILINEAR)
            self.tk_image = ImageTk.PhotoImage(resized_img)

            self.canvas.delete("all")
            self.canvas.create_image(
                dest_left + int(dest_w/2), 
                dest_top + int(dest_h/2), 
                image=self.tk_image, anchor=tk.CENTER
            )

    def on_resize(self, event):
        if hasattr(self, 'canvas') and event.widget == self.canvas:
            if self._resize_job:
                self.root.after_cancel(self._resize_job)
            self._resize_job = self.root.after(100, self.display_image)

    def next_image(self, event=None):
        if self.index < len(self.images):
            self.history.append({'action': 'next', 'index': self.index})
        self.index += 1
        self.load_image()

    def prev_image(self, event=None):
        if self.index > 0:
            self.index -= 1
            self.load_image()

    def copy_and_next(self, event=None):
        if self.index < len(self.images):
            src = os.path.join(self.current_dir, self.images[self.index])
            # 如果 SELECT 文件夹不存在则创建
            select_folder_path = self.select_folder_name if os.path.isabs(self.select_folder_name) else os.path.join(self.current_dir, self.select_folder_name)
            if not os.path.exists(select_folder_path):
                os.makedirs(select_folder_path)
            dst = os.path.join(select_folder_path, self.images[self.index])
            
            img_name = self.images[self.index]
            select_folder = self.select_folder_name
            
            def bg_copy():
                try:
                    # 复制图片并保留其原始的元信息(拍照时间等)
                    shutil.copy2(src, dst)
                    print(f"🎉 成功捕捉: {img_name} 已飞入 {select_folder} 鸟巢~ 🦉")
                    
                    # 播放✨鸟鸣✨的音效 (使用快速高低频模拟小鸟叽叽声, win专属; Mac使用系统bell)
                    if sys.platform == 'win32':
                        winsound.Beep(3000, 30)
                        winsound.Beep(3800, 30)
                        winsound.Beep(4500, 50)
                    else:
                        self.root.after(0, self.root.bell)
                except Exception as e:
                    print(f"哎呀，小鸟跑掉啦，复制文件失败 ({img_name}):\n{e}")

            # 立即写入历史记录并执行后台拷贝线程
            self.history.append({'action': 'copy', 'index': self.index, 'dst': dst})
            threading.Thread(target=bg_copy, daemon=True).start()
        
        # 复制完后自动翻下一张
        self.index += 1
        self.load_image()

    def copy_to_os_clipboard(self, event=None):
        if not self.images or self.index >= len(self.images):
            return
            
        img_path = os.path.join(self.current_dir, self.images[self.index])
        try:
            if sys.platform == 'win32':
                # 使用 PowerShell 将文件复制进剪切板 (解决转 BMP 后文件过大问题)
                ps_cmd = f"Set-Clipboard -Path '{img_path}'"
                subprocess.run(['powershell', '-command', ps_cmd], creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                
                winsound.Beep(2500, 80)
                winsound.Beep(3000, 80)
            elif sys.platform == 'darwin':
                image = Image.open(img_path)
                # macOS 使用 osascript 借助临时 TIFF 文件复制图片到剪贴板
                temp_tiff = os.path.join(self.current_dir, ".temp_clip.tiff")
                image.save(temp_tiff, "TIFF")
                script = f'set the clipboard to (read (POSIX file "{temp_tiff}") as TIFF picture)'
                subprocess.run(["osascript", "-e", script])
                try:
                    os.remove(temp_tiff)
                except:
                    pass
                self.root.bell()
            else:
                self.root.bell()
                print("暂不支持当前操作系统的直接剪贴板图片功能。")
                return
            
            # 使用临时文本提示 UI
            old_text = self.top_info_label.cget("text")
            self.top_info_label.config(text=f"✅ 成功：{self.images[self.index]} 已复制到系统剪贴板！")
            self.root.after(1500, self.update_title)  # 1.5秒后恢复标题
            
            print(f"📋 成功将 {self.images[self.index]} 复制到剪贴板。")
        except Exception as e:
            messagebox.showerror("哎呀", f"图片复制到剪贴板失败:\n{e}")

    def undo_action(self, event=None):
        if not self.history:
            messagebox.showinfo("哎呀", "没有回忆可以撤销啦！")
            return
            
        last_action = self.history.pop()
        self.index = last_action['index']
        
        if last_action['action'] == 'copy':
            dst = last_action['dst']
            try:
                if os.path.exists(dst):
                    os.remove(dst)
                    print(f"⏪ 撤销捕捉: 放飞了小鸟 {os.path.basename(dst)}")
            except Exception as e:
                print(f"撤销删除失败: {e}")
                
        self.load_image()

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)
        if self.is_fullscreen and not getattr(self, 'keep_top_bar_in_fullscreen', False):
            self.root.config(menu="")
            self.top_frame.pack_forget()
        else:
            self.root.config(menu=getattr(self, 'menubar', ""))
            self.top_frame.pack(fill=tk.X, before=self.img_frame)
        return "break"

    def exit_fullscreen(self, event=None):
        self.is_fullscreen = False
        self.root.attributes("-fullscreen", False)
        self.root.config(menu=getattr(self, 'menubar', ""))
        self.top_frame.pack(fill=tk.X, before=self.img_frame)
        return "break"

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw() # 隐藏主窗口
    
    import os
    icon_path = 'bird.ico'
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller 运行时提取路径
        icon_path = os.path.join(sys._MEIPASS, 'bird.ico')
    elif os.path.exists('bird.ico'):
        icon_path = 'bird.ico'
        
    # 显示干净的 loading 弹窗
    splash = tk.Toplevel(root)
    splash.overrideredirect(True) # 去除边框
    splash_w, splash_h = 240, 160
    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    splash.geometry(f"{splash_w}x{splash_h}+{int((screen_w-splash_w)/2)}+{int((screen_h-splash_h)/2)}")
    splash.configure(bg="#E8F5E9")

    try:
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
            from PIL import Image, ImageTk
            img = Image.open(icon_path).resize((64, 64), Image.Resampling.LANCZOS)
            tk_img = ImageTk.PhotoImage(img) # 保留引用
            tk.Label(splash, image=tk_img, bg="#E8F5E9").pack(pady=(20, 10))
    except Exception:
        pass

    tk.Label(splash, text="LOADING...", font=("Microsoft YaHei", 12, "bold"), bg="#E8F5E9", fg="#2E7D32").pack(pady=5)
    
    splash.update() # 渲染 loading 界面

    # 在后台短暂延迟后开始主程序初始化并销毁闪屏
    def init_app():
        app = ImageViewer(root)
        splash.destroy()
        root.deiconify() # 显示出真正的应用窗口
        
    root.after(100, init_app)
    root.mainloop()
