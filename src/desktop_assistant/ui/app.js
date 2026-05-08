const params = new URLSearchParams(window.location.search);
const windowMode = params.get("mode") === "main" ? "main" : "avatar";
const isAvatarWindow = windowMode === "avatar";
const isMainWindow = windowMode === "main";
document.body.dataset.mode = windowMode;

const canvas = document.getElementById("avatarCanvas");
const miniPopup = document.getElementById("miniPopup");
const miniBubbleText = document.getElementById("miniBubbleText");
const miniForm = document.getElementById("miniForm");
const miniInput = document.getElementById("miniInput");
const miniSend = document.getElementById("miniSend");
const openMainFromMini = document.getElementById("openMainFromMini");
const chatPopup = document.getElementById("chatPopup");
const panel = document.getElementById("panel");
const avatarHit = document.getElementById("avatarHit");
const avatarToolbar = document.getElementById("avatarToolbar");
const toolbarPin = document.getElementById("toolbarPin");
const toolbarChat = document.getElementById("toolbarChat");
const toolbarSettings = document.getElementById("toolbarSettings");
const toolbarMinimize = document.getElementById("toolbarMinimize");
const connectionBadge = document.getElementById("connectionBadge");
const closeChat = document.getElementById("closeChat");
const openPanel = document.getElementById("openPanel");
const openChat = document.getElementById("openChat");
const closePanel = document.getElementById("closePanel");
const messages = document.getElementById("messages");
const chatForm = document.getElementById("chatForm");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const profileSelect = document.getElementById("profileSelect");
const profileName = document.getElementById("profileName");
const createProfile = document.getElementById("createProfile");
const renameProfile = document.getElementById("renameProfile");
const deleteProfile = document.getElementById("deleteProfile");
const modelSearch = document.getElementById("modelSearch");
const modelSelect = document.getElementById("modelSelect");
const rendererStatus = document.getElementById("rendererStatus");
const contextStatus = document.getElementById("contextStatus");
const contextPreview = document.getElementById("contextPreview");
const refreshContext = document.getElementById("refreshContext");
const providerText = document.getElementById("providerText");
const personaStatus = document.getElementById("personaStatus");
const memoryStatus = document.getElementById("memoryStatus");
const modelSourceStatus = document.getElementById("modelSourceStatus");
const permissionStatus = document.getElementById("permissionStatus");
const permissionPolicyStatus = document.getElementById("permissionPolicyStatus");
const confirmationStatus = document.getElementById("confirmationStatus");
const autonomyStatus = document.getElementById("autonomyStatus");
const chatTitle = document.getElementById("chatTitle");
const avatarScaleInput = document.getElementById("avatarScale");
const avatarScaleValue = document.getElementById("avatarScaleValue");
const avatarAlwaysOnTop = document.getElementById("avatarAlwaysOnTop");
const autonomyEnabled = document.getElementById("autonomyEnabled");
const autonomyWindow = document.getElementById("autonomyWindow");
const autonomyMaxMessages = document.getElementById("autonomyMaxMessages");
const autonomyMinInterval = document.getElementById("autonomyMinInterval");
const autonomyMaxInterval = document.getElementById("autonomyMaxInterval");
const memoryAutoExtract = document.getElementById("memoryAutoExtract");
const memoryAutoMaxEntries = document.getElementById("memoryAutoMaxEntries");
const personaName = document.getElementById("personaName");
const personaPersonality = document.getElementById("personaPersonality");
const personaSpeakingStyle = document.getElementById("personaSpeakingStyle");
const saveSettings = document.getElementById("saveSettings");
const settingsSaveStatus = document.getElementById("settingsSaveStatus");
const mainResizeGrip = document.getElementById("mainResizeGrip");
const permissionControls = Array.from(document.querySelectorAll("[data-permission-key]"));

let bridge = null;
let activeAssistantMessage = null;
let state = { models: [], active_model_id: null };
const handledConfirmations = new Set();
let currentWindowFrame = null;
let pendingSettingsPayload = null;
let pendingSettingsTimer = null;
let settingsStatusTimer = null;
let bubbleHideTimer = null;
let badgeHideTimer = null;
let measuredMiniHeight = 164;
let bubblePlacement = "bottom";

const avatarTransform = {
  scale: Number(localStorage.getItem("avatar_scale") || 1),
};
const layout = {
  avatarBaseWidth: 320,
  avatarBaseHeight: 420,
  avatarMarginX: 24,
  avatarMarginBottom: 18,
  miniGap: 8,
  miniDefaultHeight: 164,
  bubbleScreenPadding: 10,
};

class RendererManager {
  constructor(canvasElement, statusElement) {
    this.canvas = canvasElement;
    this.status = statusElement;
    this.app = null;
    this.fallbackRaf = null;
    this.fallbackFrame = 0;
    this._canvas2DUsed = false;
    this.loadedScripts = new Set();
    this.missingVendorFiles = [];
    this.currentModelId = null;
    this.currentRenderFailed = false;
    this.generation = 0;
    this.rendererMode = "";
    this.tickerCallbacks = [];
    this.cleanupCallbacks = [];
  }

  async render(model) {
    if (!this.canvas) return;
    const nextModelId = model?.id || null;
    if (nextModelId && nextModelId === this.currentModelId && this.app && !this.currentRenderFailed) {
      return;
    }
    if (!nextModelId && this.currentModelId === null && this.fallbackRaf && !this.currentRenderFailed) {
      return;
    }
    const generation = ++this.generation;
    this.destroy();
    this._replaceCanvas();
    this._canvas2DUsed = false;
    this.missingVendorFiles = [];
    this.currentModelId = nextModelId;
    this.currentRenderFailed = false;
    hideConnectionBadge();
    if (!model) {
      this.startFallback("未发现模型");
      return;
    }
    try {
      await this.loadScript("./vendor/pixi.min.js");
      if (model.kind === "live2d") {
        await this.renderLive2D(model, generation);
      } else if (model.kind === "spine38") {
        await this.renderSpine(model, generation);
      } else {
        this.startFallback("不支持的模型");
      }
    } catch (error) {
      const message = this.errorMessage(error);
      this.currentRenderFailed = true;
      this.destroy();
      this.startFallback(`${model.kind} fallback: ${message}`);
      showConnectionBadge(`✧ 形象加载失败：${message}`, { timeout: 9000 });
      console.error("Avatar render failed", error);
    }
  }

  destroy() {
    if (!this.canvas) return;
    if (this.fallbackRaf) {
      cancelAnimationFrame(this.fallbackRaf);
      this.fallbackRaf = null;
    }
    for (const { app, callback } of this.tickerCallbacks) {
      app.ticker?.remove?.(callback);
    }
    this.tickerCallbacks = [];
    for (const cleanup of this.cleanupCallbacks) {
      cleanup();
    }
    this.cleanupCallbacks = [];
    if (this.app) {
      try {
        this.app.destroy(false, { children: true, texture: false, baseTexture: false });
      } catch (error) {
        console.warn("PIXI destroy failed", error);
      }
      this.app = null;
    }
    this.rendererMode = "";
  }

  _replaceCanvas() {
    const old = this.canvas;
    const fresh = document.createElement("canvas");
    fresh.id = old.id;
    fresh.width = old.width;
    fresh.height = old.height;
    fresh.className = old.className;
    for (const attr of old.attributes) {
      if (!fresh.hasAttribute(attr.name)) {
        fresh.setAttribute(attr.name, attr.value);
      }
    }
    old.replaceWith(fresh);
    this.canvas = fresh;
  }

  _ensureWebGLCanvas() {
    if (!this._canvas2DUsed) return;
    this._replaceCanvas();
    this._canvas2DUsed = false;
  }

  async loadScript(src) {
    if (this.loadedScripts.has(src) || document.querySelector(`script[data-src="${src}"]`)) {
      this.loadedScripts.add(src);
      return;
    }
    return new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = src;
      script.dataset.src = src;
      script.onload = () => {
        this.loadedScripts.add(src);
        resolve();
      };
      script.onerror = () => {
        this.missingVendorFiles.push(src.replace("./vendor/", ""));
        reject(new Error(`missing ${src}`));
      };
      document.head.appendChild(script);
    });
  }

  errorMessage(error) {
    if (!error) return "unknown error";
    if (typeof error === "string") return error;
    if (error.message) return error.message;
    return String(error);
  }

  createPixiApp({ allowCanvasFallback = true } = {}) {
    this._ensureWebGLCanvas();
    const options = this.pixiOptions();
    try {
      this.app = new PIXI.Application(options);
    } catch (error) {
      if (!allowCanvasFallback) {
        this._replaceCanvas();
        this._canvas2DUsed = false;
        try {
          this.app = new PIXI.Application(this.pixiOptions());
        } catch (retryError) {
          throw new Error(`WebGL: ${this.errorMessage(error)} / retry: ${this.errorMessage(retryError)}`);
        }
      } else {
        if (!PIXI.CanvasRenderer) {
          throw error;
        }
        console.warn("PIXI WebGL unavailable, using CanvasRenderer", error);
        this._replaceCanvas();
        this._canvas2DUsed = false;
        try {
          this.app = new PIXI.Application({ ...this.pixiOptions(), forceCanvas: true });
        } catch (canvasError) {
          throw new Error(`WebGL: ${this.errorMessage(error)} / Canvas: ${this.errorMessage(canvasError)}`);
        }
      }
    }
    this.rendererMode =
      this.app.renderer?.type === PIXI.RENDERER_TYPE?.CANVAS ? "Canvas" : "WebGL";
    if (!allowCanvasFallback && this.rendererMode !== "WebGL") {
      const mode = this.rendererMode || "unknown";
      this.app.destroy(false, { children: true, texture: false, baseTexture: false });
      this.app = null;
      throw new Error(`Live2D requires WebGL, current renderer is ${mode}`);
    }
    return this.app;
  }

  pixiOptions() {
    return {
      view: this.canvas,
      transparent: true,
      backgroundAlpha: 0,
      antialias: true,
      autoStart: true,
      width: this.canvas.width,
      height: this.canvas.height,
    };
  }

  addTicker(callback) {
    if (!this.app?.ticker) {
      return;
    }
    this.app.ticker.add(callback);
    this.app.ticker.start();
    this.tickerCallbacks.push({ app: this.app, callback });
  }

  rendererSuffix() {
    return this.rendererMode ? ` (${this.rendererMode})` : "";
  }

  pickSpineAnimation(animations) {
    const candidates = (animations || []).filter((animation) => animation?.duration > 0);
    if (!candidates.length) {
      return null;
    }
    const preferred = [
      /idle/i,
      /relax/i,
      /loop/i,
      /wait/i,
      /breath/i,
      /stand/i,
      /home/i,
      /default/i,
    ];
    for (const pattern of preferred) {
      const match = candidates.find((animation) => pattern.test(animation.name || ""));
      if (match) {
        return match;
      }
    }
    return candidates.reduce((best, animation) => (animation.duration > best.duration ? animation : best));
  }

  fitToCanvas(displayObject, coverage = 0.9) {
    const bounds = displayObject.getLocalBounds?.();
    if (!bounds || bounds.width <= 0 || bounds.height <= 0) {
      displayObject.x = this.canvas.width / 2;
      displayObject.y = this.canvas.height * 0.75;
      return;
    }
    const scale = Math.min(
      (this.canvas.width * coverage) / bounds.width,
      (this.canvas.height * coverage) / bounds.height,
    );
    const centerX = bounds.x + bounds.width / 2;
    const centerY = bounds.y + bounds.height / 2;
    displayObject.scale.set(scale);
    displayObject.x = this.canvas.width / 2 - centerX * scale;
    displayObject.y = this.canvas.height / 2 - centerY * scale;
  }

  startFallback(label = "fallback") {
    if (!this.canvas) return;
    const missing = this.missingVendorFiles.length ? ` (${this.missingVendorFiles.join(", ")})` : "";
    if (this.status) {
      this.status.textContent = `${label}${missing}`;
    }
    if (!this._canvas2DUsed) {
      this._replaceCanvas();
    }
    const ctx = this.canvas.getContext("2d");
    this._canvas2DUsed = true;
    if (!ctx) {
      return;
    }
    const w = this.canvas.width;
    const h = this.canvas.height;

    const draw = () => {
      this.fallbackFrame += 0.03;
      ctx.clearRect(0, 0, w, h);
      const bob = Math.sin(this.fallbackFrame) * 7;

      ctx.save();
      ctx.translate(w / 2, h / 2 + bob);

      const body = ctx.createLinearGradient(-80, -40, 80, 135);
      body.addColorStop(0, "#f8fafc");
      body.addColorStop(1, "#c7dedc");
      ctx.fillStyle = body;
      ctx.beginPath();
      ctx.ellipse(0, 68, 74, 112, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#edf7f6";
      ctx.beginPath();
      ctx.ellipse(0, -44, 84, 88, 0, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#26323b";
      ctx.beginPath();
      ctx.arc(-30, -48, 8, 0, Math.PI * 2);
      ctx.arc(30, -48, 8, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = "#0b7a75";
      ctx.lineWidth = 5;
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.arc(0, -22, 24, 0.15, Math.PI - 0.15);
      ctx.stroke();

      ctx.strokeStyle = "#8cb8b5";
      ctx.lineWidth = 8;
      ctx.beginPath();
      ctx.moveTo(-62, 44);
      ctx.quadraticCurveTo(-106, 80, -84, 132);
      ctx.moveTo(62, 44);
      ctx.quadraticCurveTo(106, 80, 84, 132);
      ctx.stroke();

      ctx.restore();
      this.fallbackRaf = requestAnimationFrame(draw);
    };
    draw();
  }

  async renderLive2D(model, generation) {
    await this.loadScript("./vendor/live2dcubismcore.min.js");
    await this.loadScript("./vendor/pixi-live2d-display.min.js");
    if (!window.Live2DCubismCore) {
      throw new Error("Live2DCubismCore unavailable");
    }
    if (!window.PIXI?.live2d?.Live2DModel) {
      throw new Error("pixi-live2d-display unavailable");
    }
    if (window.PIXI.live2d.config) {
      const warningLevel =
        window.PIXI.live2d.config.LOG_LEVEL_WARNING ?? window.PIXI.live2d.LogLevel?.LogLevel_Warning;
      if (warningLevel !== undefined) {
        window.PIXI.live2d.config.logLevel = warningLevel;
      }
    }
    if (window.PIXI.live2d.cubism4Ready) {
      await window.PIXI.live2d.cubism4Ready();
    }
    const app = this.createPixiApp({ allowCanvasFallback: false });
    if (this.status) {
      this.status.textContent = "Live2D 加载中";
    }
    const avatar = await this.loadLive2DModel(model);
    if (generation !== this.generation) {
      avatar.destroy?.();
      return;
    }
    this.fitLive2DToCanvas(avatar);
    this.attachLive2DInteractions(avatar, model);
    app.stage.addChild(avatar);
    this.currentRenderFailed = false;
    const expressionCount = model.metadata?.live2d?.expressions?.length || 0;
    if (this.status) {
      this.status.textContent = `Live2D${this.rendererSuffix()} / ${expressionCount} 表情`;
    }
    hideConnectionBadge();
  }

  async loadLive2DModel(model) {
    let settingsError = null;
    try {
      const source = await this.live2DSource(model);
      return await PIXI.live2d.Live2DModel.from(source, { autoInteract: false });
    } catch (error) {
      settingsError = error;
      console.warn("Live2D settings object loading failed, retrying with URL", error);
    }
    try {
      return await PIXI.live2d.Live2DModel.from(model.entry_url, { autoInteract: false });
    } catch (urlError) {
      throw new Error(`JSON: ${this.errorMessage(settingsError)} / URL: ${this.errorMessage(urlError)}`);
    }
  }

  async live2DSource(model) {
    const response = await fetch(model.entry_url);
    if (!response.ok && response.status !== 0) {
      throw new Error(`model JSON HTTP ${response.status}`);
    }
    const settings = await response.json();
    settings.url = model.entry_url;
    settings.FileReferences = settings.FileReferences || {};
    const expressions = model.metadata?.live2d?.expressions || [];
    if (expressions.length && !settings.FileReferences.Expressions?.length) {
      settings.FileReferences.Expressions = expressions.map((expression) => ({
        Name: expression.name,
        File: expression.file,
      }));
    }
    return settings;
  }

  fitLive2DToCanvas(avatar) {
    avatar.anchor?.set?.(0.5, 0.5);
    const internalWidth = Number(avatar.internalModel?.width);
    const internalHeight = Number(avatar.internalModel?.height);
    const bounds = avatar.getLocalBounds?.();
    const width = Number.isFinite(internalWidth) && internalWidth > 0 ? internalWidth : bounds?.width || avatar.width;
    const height = Number.isFinite(internalHeight) && internalHeight > 0 ? internalHeight : bounds?.height || avatar.height;
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
      avatar.scale.set(1);
      avatar.x = this.canvas.width / 2;
      avatar.y = this.canvas.height / 2;
      return;
    }
    const scale = Math.min(this.canvas.width / width, this.canvas.height / height) * 0.92;
    avatar.scale.set(scale);
    avatar.x = this.canvas.width / 2;
    avatar.y = this.canvas.height / 2;
  }

  attachLive2DInteractions(avatar, model) {
    const expressions = model.metadata?.live2d?.expressions || [];
    if (expressions.length) {
      const cheerful = expressions.find((item) => /blush|heart|starry|yeah|keep/i.test(item.name || ""));
      avatar.expression?.(cheerful?.name || expressions[0].name).catch?.(() => {});
    }
    const focusHandler = (event) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      const y = ((event.clientY - rect.top) / rect.height) * -2 + 1;
      avatar.focus?.(x, y);
    };
    const clickHandler = () => {
      if (!expressions.length) return;
      const next = expressions[Math.floor(Math.random() * expressions.length)];
      avatar.expression?.(next.name).catch?.(() => {});
    };
    const target = this.canvas;
    target.addEventListener("pointermove", focusHandler);
    target.addEventListener("click", clickHandler);
    this.cleanupCallbacks.push(() => {
      target.removeEventListener("pointermove", focusHandler);
      target.removeEventListener("click", clickHandler);
    });
  }

  async renderSpine(model, generation) {
    await this.loadScript("./vendor/pixi-spine.umd.js");
    if (!window.PIXI?.spine?.Spine) {
      throw new Error("pixi-spine unavailable");
    }
    const app = this.createPixiApp();
    if (this.status) {
      this.status.textContent = `Spine 3.8${this.rendererSuffix()}`;
    }
    const loader = new PIXI.Loader();
    const metadata = {};
    if (model.assets?.atlas_url) {
      metadata.spineAtlasFile = model.assets.atlas_url;
    }
    if (model.assets?.png_url) {
      const texture = PIXI.Texture.from(model.assets.png_url);
      const pageName = this.assetBasename(model.assets.png);
      if (pageName) {
        metadata.images = { [pageName]: texture, default: texture };
      }
      metadata.image = texture;
    }
    loader.add(model.id, model.assets?.skel_url || model.entry_url, { metadata });
    loader.load((loaderInstance, resources) => {
      if (generation !== this.generation) {
        return;
      }
      const resource = resources[model.id];
      if (!resource?.spineData) {
        this.currentRenderFailed = true;
        this.destroy();
        this.startFallback("Spine 加载失败");
        return;
      }
      const avatar = new PIXI.spine.Spine(resource.spineData);
      const animations = avatar.spineData.animations || [];
      const animation = this.pickSpineAnimation(animations);
      if (animation) {
        avatar.autoUpdate = false;
        avatar.state.setAnimation(0, animation.name, true);
        avatar.update(0);
        this.addTicker(() => {
          const deltaSeconds = app.ticker?.deltaMS ? app.ticker.deltaMS / 1000 : 1 / 60;
          avatar.update(Math.min(deltaSeconds, 1 / 15));
        });
        if (this.status) {
          this.status.textContent = `Spine 3.8${this.rendererSuffix()} / ${animation.name}`;
        }
      } else if (this.status) {
        this.status.textContent = `Spine 3.8${this.rendererSuffix()} / 无动画`;
      }
      this.fitToCanvas(avatar);
      app.stage.addChild(avatar);
      this.currentRenderFailed = false;
    });
  }

  assetBasename(path) {
    if (!path || typeof path !== "string") return "";
    return path.split(/[\\/]/).pop() || "";
  }
}

const renderer = new RendererManager(canvas, rendererStatus);

function clampScale(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 1;
  return Math.max(0.35, Math.min(2.5, number));
}

function syncScaleControl() {
  const scale = clampScale(avatarTransform.scale);
  if (avatarScaleInput) {
    avatarScaleInput.value = String(scale);
  }
  if (avatarScaleValue) {
    avatarScaleValue.textContent = `${Math.round(scale * 100)}%`;
  }
}

function stageStyle(name, value) {
  document.documentElement.style.setProperty(name, value);
  document.getElementById("app")?.style.setProperty(name, value);
}

function avatarMetrics() {
  const scale = clampScale(avatarTransform.scale);
  return {
    width: Math.round(layout.avatarBaseWidth * scale),
    height: Math.round(layout.avatarBaseHeight * scale),
  };
}

function bubbleMetrics(avatarWidth) {
  const width = Math.min(360, Math.max(260, Math.round(avatarWidth * 1.02)));
  const left = Math.max(12, layout.avatarMarginX + Math.round((avatarWidth - width) / 2));
  return { width, left };
}

function currentMiniHeight() {
  if (!miniVisible()) {
    return 0;
  }
  const height = Math.ceil(miniPopup.getBoundingClientRect().height || layout.miniDefaultHeight);
  measuredMiniHeight = Math.max(layout.miniDefaultHeight, height + 14);
  return measuredMiniHeight;
}

function screenBounds() {
  const top = Number.isFinite(Number(window.screen?.availTop)) ? Number(window.screen.availTop) : 0;
  const height = Number(window.screen?.availHeight || window.screen?.height || 900);
  return { top, bottom: top + height };
}

function nextBubblePlacement(avatarHeight, bubbleHeight) {
  if (!miniVisible() || bubbleHeight <= 0) {
    return "bottom";
  }
  const bounds = screenBounds();
  const frameY = currentFrameValue("y", state.settings?.ui?.avatar_y || window.screenY || 0);
  const bottomNeeded = frameY + avatarHeight + layout.miniGap + bubbleHeight + layout.avatarMarginBottom;
  const hasRoomAbove = frameY - bounds.top >= bubbleHeight + layout.miniGap + layout.bubbleScreenPadding;
  return bottomNeeded > bounds.bottom - layout.bubbleScreenPadding && hasRoomAbove ? "top" : "bottom";
}

function syncAvatarLayout() {
  avatarTransform.scale = clampScale(avatarTransform.scale);
  const avatarWidth = Math.round(layout.avatarBaseWidth * avatarTransform.scale);
  const avatarHeight = Math.round(layout.avatarBaseHeight * avatarTransform.scale);
  const { width: bubbleWidth, left: bubbleLeft } = bubbleMetrics(avatarWidth);
  const bubbleHeight = currentMiniHeight();
  bubblePlacement = nextBubblePlacement(avatarHeight, bubbleHeight);
  const stageTop = miniVisible() && bubblePlacement === "top" ? bubbleHeight + layout.miniGap : 0;
  const bubbleTop = bubblePlacement === "top" ? 0 : stageTop + avatarHeight + layout.miniGap;
  stageStyle("--avatar-width", `${avatarWidth}px`);
  stageStyle("--avatar-height", `${avatarHeight}px`);
  stageStyle("--stage-top", `${stageTop}px`);
  stageStyle("--bubble-top", `${bubbleTop}px`);
  stageStyle("--bubble-width", `${bubbleWidth}px`);
  stageStyle("--bubble-left", `${bubbleLeft}px`);
  stageStyle("--bubble-tail-left", `${Math.max(32, Math.round(bubbleWidth * 0.16))}px`);
  if (miniPopup) {
    miniPopup.dataset.placement = bubblePlacement;
  }
}

function applyAvatarTransform() {
  syncAvatarLayout();
  localStorage.setItem("avatar_scale", String(avatarTransform.scale));
  syncScaleControl();
  resizeAvatarWindow();
}

function miniVisible() {
  return isAvatarWindow && miniPopup && !miniPopup.hidden;
}

function desiredAvatarWindowSize() {
  syncAvatarLayout();
  const { width: avatarWidth, height: avatarHeight } = avatarMetrics();
  const { width: bubbleWidth } = bubbleMetrics(avatarWidth);
  const bubbleHeight = miniVisible() ? measuredMiniHeight + layout.miniGap : 0;
  return {
    width: Math.max(layout.avatarMarginX * 2 + avatarWidth, bubbleWidth + layout.avatarMarginX * 2),
    height: avatarHeight + layout.avatarMarginBottom + bubbleHeight,
  };
}

function resizeAvatarWindow() {
  if (!isAvatarWindow || !bridge?.resizeWindow) return;
  const { width, height } = desiredAvatarWindowSize();
  bridge.resizeWindow(width, height, (payload) => {
    storeWindowFrame(parseJson(payload));
  });
}

function storeWindowFrame(frame) {
  if (!frame || typeof frame !== "object") return;
  currentWindowFrame = frame;
}

function restoreWindowPosition() {
  if (!bridge?.setWindowPosition) return;
  const ui = state.settings?.ui || {};
  const x = Number(isAvatarWindow ? ui.avatar_x : ui.main_x);
  const y = Number(isAvatarWindow ? ui.avatar_y : ui.main_y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return;
  if (x === 0 && y === 0) return;
  bridge.setWindowPosition(Math.round(x), Math.round(y), (payload) => {
    storeWindowFrame(parseJson(payload));
  });
}

function mergeSettingsPayload(target, source) {
  for (const [key, value] of Object.entries(source || {})) {
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      target[key] &&
      typeof target[key] === "object" &&
      !Array.isArray(target[key])
    ) {
      mergeSettingsPayload(target[key], value);
    } else if (value && typeof value === "object" && !Array.isArray(value)) {
      target[key] = { ...value };
    } else {
      target[key] = value;
    }
  }
  return target;
}

function setSettingsStatus(text, isError = false) {
  if (!settingsSaveStatus) return;
  settingsSaveStatus.textContent = text;
  settingsSaveStatus.style.color = isError ? "#b42318" : "";
  if (settingsStatusTimer) {
    clearTimeout(settingsStatusTimer);
  }
  if (text && !isError) {
    settingsStatusTimer = setTimeout(() => {
      settingsSaveStatus.textContent = "";
    }, 2600);
  }
}

function setPinnedControlState(pinned) {
  if (toolbarPin) {
    toolbarPin.classList.toggle("active", pinned);
    toolbarPin.setAttribute("aria-pressed", String(pinned));
  }
  if (avatarAlwaysOnTop) {
    avatarAlwaysOnTop.checked = pinned;
  }
}

function setPinPending(pending) {
  if (toolbarPin) {
    toolbarPin.disabled = pending;
    toolbarPin.classList.toggle("pending", pending);
    toolbarPin.setAttribute("aria-busy", String(pending));
  }
  if (avatarAlwaysOnTop) {
    avatarAlwaysOnTop.disabled = pending;
  }
}

function savePinnedState(pinned) {
  setPinPending(true);
  setPinnedControlState(pinned);
  saveSettingsPayload(
    { ui: { avatar_always_on_top: pinned } },
    {
      successText: pinned ? "已置顶" : "已取消置顶",
      onComplete: (result) => {
        setPinPending(false);
        if (!result.ok) {
          setPinnedControlState(state.settings?.ui?.avatar_always_on_top !== false);
        }
      },
    },
  );
}

function hideConnectionBadge() {
  if (!connectionBadge) return;
  if (badgeHideTimer) {
    clearTimeout(badgeHideTimer);
    badgeHideTimer = null;
  }
  connectionBadge.hidden = true;
  connectionBadge.textContent = "";
}

function showConnectionBadge(text, options = {}) {
  if (!connectionBadge) return;
  if (badgeHideTimer) {
    clearTimeout(badgeHideTimer);
    badgeHideTimer = null;
  }
  connectionBadge.textContent = text;
  connectionBadge.hidden = false;
  const timeout = Number(options.timeout || 0);
  if (timeout > 0) {
    badgeHideTimer = setTimeout(() => {
      hideConnectionBadge();
    }, timeout);
  }
}

function saveSettingsPayload(payload, options = {}) {
  if (!bridge?.saveSettings) {
    options.onComplete?.({ ok: false, error: "未连接 Qt bridge" });
    return;
  }
  if (options.showStatus) {
    setSettingsStatus("保存中");
  }
  bridge.saveSettings(JSON.stringify(payload), (response) => {
    const result = parseJson(response);
    if (result.state) {
      updateState(result.state);
    }
    if (result.ok) {
      setSettingsStatus(options.successText || "已保存");
    } else {
      setSettingsStatus(result.error || "保存失败", true);
    }
    options.onComplete?.(result);
  });
}

function handleProfileResponse(response, successText) {
  const result = parseJson(response);
  if (result.state) {
    updateState(result.state);
  }
  if (result.ok) {
    setSettingsStatus(successText);
  } else {
    setSettingsStatus(result.error || "存档操作失败", true);
  }
}

function queueSettingsSave(payload) {
  pendingSettingsPayload = mergeSettingsPayload(pendingSettingsPayload || {}, payload);
  if (pendingSettingsTimer) {
    clearTimeout(pendingSettingsTimer);
  }
  pendingSettingsTimer = setTimeout(() => {
    const nextPayload = pendingSettingsPayload;
    pendingSettingsPayload = null;
    saveSettingsPayload(nextPayload, { successText: "已自动保存" });
  }, 450);
}

function currentFrameValue(name, fallback) {
  const value = Number(currentWindowFrame?.[name]);
  return Number.isFinite(value) ? value : fallback;
}

function persistWindowFrame() {
  if (!currentWindowFrame) return;
  const ui = state.settings?.ui || {};
  const payload = isAvatarWindow
    ? {
        ui: {
          avatar_x: Math.round(currentFrameValue("x", ui.avatar_x || 0)),
          avatar_y: Math.round(currentFrameValue("y", ui.avatar_y || 0)),
        },
      }
    : {
        ui: {
          main_x: Math.round(currentFrameValue("x", ui.main_x || 0)),
          main_y: Math.round(currentFrameValue("y", ui.main_y || 0)),
          main_width: Math.round(currentFrameValue("width", ui.main_width || window.innerWidth)),
          main_height: Math.round(currentFrameValue("height", ui.main_height || window.innerHeight)),
        },
      };
  saveSettingsPayload(payload, { successText: isAvatarWindow ? "位置已保存" : "窗口已保存" });
}

function clearBubbleHideTimer() {
  if (bubbleHideTimer) {
    clearTimeout(bubbleHideTimer);
    bubbleHideTimer = null;
  }
}

function scheduleBubbleAutoHide(delay = 10000) {
  if (!isAvatarWindow) return;
  clearBubbleHideTimer();
  bubbleHideTimer = setTimeout(() => {
    if (document.activeElement === miniInput || miniInput?.value.trim()) {
      scheduleBubbleAutoHide(delay);
      return;
    }
    hideMiniPopup();
  }, delay);
}

function showMiniPopup(options = {}) {
  if (!miniPopup) return;
  const shouldFocus = options.focus !== false;
  miniPopup.hidden = false;
  syncAvatarLayout();
  resizeAvatarWindow();
  clearBubbleHideTimer();
  if (shouldFocus) {
    miniInput?.focus();
  }
}

function hideMiniPopup() {
  if (!miniPopup) return;
  clearBubbleHideTimer();
  miniPopup.hidden = true;
  syncAvatarLayout();
  resizeAvatarWindow();
}

function setBubbleText(text, role = "assistant") {
  if (!miniBubbleText) return null;
  miniPopup.dataset.role = role;
  miniBubbleText.textContent = text;
  showMiniPopup({ focus: false });
  return miniBubbleText;
}

function showChatPopup() {
  if (chatPopup) chatPopup.hidden = false;
  if (panel) {
    panel.hidden = true;
    panel.classList.remove("settings-panel");
  }
  messageInput?.focus();
}

function showSettingsPanel() {
  if (chatPopup) chatPopup.hidden = true;
  if (panel) {
    panel.hidden = false;
    panel.classList.add("settings-panel");
  }
}

function parseJson(value, fallback = {}) {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

function currentMessageContainer() {
  return isAvatarWindow ? miniBubbleText : messages;
}

function appendMessage(role, text = "") {
  if (isAvatarWindow) {
    return setBubbleText(text, role);
  }
  const container = currentMessageContainer();
  if (!container) return null;
  const item = document.createElement("div");
  item.className = `message ${role}`;
  item.textContent = text;
  container.appendChild(item);
  container.scrollTop = container.scrollHeight;
  return item;
}

function setBusy(value) {
  if (sendButton) {
    sendButton.disabled = value;
    sendButton.textContent = value ? "处理中" : "发送";
  }
  if (miniSend) {
    miniSend.disabled = value;
    miniSend.textContent = value ? "…" : "↵";
  }
}

function normalizePermission(value) {
  const normalized = String(value || "allow").toLowerCase();
  return ["allow", "ask", "deny"].includes(normalized) ? normalized : "allow";
}

function permissionText(value) {
  const normalized = normalizePermission(value);
  if (normalized === "ask") return "询问";
  if (normalized === "deny") return "禁用";
  return "允许";
}

function summarizePermissionMap(values) {
  const entries = Object.entries(values || {});
  if (!entries.length) return "未知";
  return entries.map(([key, value]) => `${key}:${permissionText(value)}`).join(" / ");
}

function populatePermissionControls() {
  const policy = state.settings?.permissions || {};
  for (const control of permissionControls) {
    const key = control.dataset.permissionKey;
    if (!key) continue;
    control.value = normalizePermission(policy[key]);
  }
}

function collectPermissionSettings() {
  const permissions = {};
  for (const control of permissionControls) {
    const key = control.dataset.permissionKey;
    if (!key) continue;
    permissions[key] = normalizePermission(control.value);
  }
  return permissions;
}

function populateProfileForm() {
  const profile = state.settings?.profile || {};
  const profiles = Array.isArray(profile.profiles) ? profile.profiles : [];
  if (profileSelect) {
    profileSelect.innerHTML = "";
    for (const item of profiles) {
      const option = document.createElement("option");
      option.value = item.id || "";
      option.textContent = item.name || item.id || "未命名";
      option.selected = item.id === profile.active_id;
      profileSelect.appendChild(option);
    }
  }
  if (profileName) {
    profileName.value = profile.name || "";
  }
}

function populateSettingsForm() {
  populateProfileForm();
  populatePermissionControls();
  const ui = state.settings?.ui || {};
  if (avatarAlwaysOnTop) {
    avatarAlwaysOnTop.checked = ui.avatar_always_on_top !== false;
  }
  const autonomy = state.settings?.autonomy || {};
  if (autonomyEnabled) {
    autonomyEnabled.checked = Boolean(autonomy.enabled);
  }
  if (autonomyWindow) {
    autonomyWindow.value = String(Math.max(60, Number(autonomy.window_seconds || 600)));
  }
  if (autonomyMaxMessages) {
    autonomyMaxMessages.value = String(Math.max(1, Number(autonomy.max_messages_per_window || 3)));
  }
  if (autonomyMinInterval) {
    autonomyMinInterval.value = String(Math.max(30, Number(autonomy.min_interval_seconds || 60)));
  }
  if (autonomyMaxInterval) {
    autonomyMaxInterval.value = String(Math.max(30, Number(autonomy.max_interval_seconds || 180)));
  }
  const memory = state.settings?.memory || {};
  if (memoryAutoExtract) {
    memoryAutoExtract.checked = memory.auto_extract_enabled !== false;
  }
  if (memoryAutoMaxEntries) {
    memoryAutoMaxEntries.value = String(Math.max(0, Number(memory.auto_extract_max_entries ?? 3)));
  }

  const persona = state.settings?.persona || {};
  if (personaName) {
    personaName.value = persona.name || "";
  }
  if (personaPersonality) {
    personaPersonality.value = persona.personality || "";
  }
  if (personaSpeakingStyle) {
    personaSpeakingStyle.value = persona.speaking_style || "";
  }
}

function collectSettingsForm() {
  const ui = state.settings?.ui || {};
  const minInterval = Math.max(30, Number(autonomyMinInterval?.value || 60));
  const maxInterval = Math.max(minInterval, Number(autonomyMaxInterval?.value || 180));
  const selectedModelId =
    modelSelect?.value || state.active_model_id || state.settings?.models?.default_id || "";
  return {
    models: {
      default_id: selectedModelId,
    },
    ui: {
      avatar_scale: clampScale(avatarTransform.scale),
      avatar_always_on_top: avatarAlwaysOnTop?.checked ?? state.settings?.ui?.avatar_always_on_top ?? true,
      avatar_x: Math.round(isAvatarWindow ? currentFrameValue("x", ui.avatar_x || 0) : ui.avatar_x || 0),
      avatar_y: Math.round(isAvatarWindow ? currentFrameValue("y", ui.avatar_y || 0) : ui.avatar_y || 0),
      main_x: Math.round(isMainWindow ? currentFrameValue("x", ui.main_x || 0) : ui.main_x || 0),
      main_y: Math.round(isMainWindow ? currentFrameValue("y", ui.main_y || 0) : ui.main_y || 0),
      main_width: Math.round(isMainWindow ? currentFrameValue("width", ui.main_width || window.innerWidth) : ui.main_width || 560),
      main_height: Math.round(isMainWindow ? currentFrameValue("height", ui.main_height || window.innerHeight) : ui.main_height || 640),
    },
    autonomy: {
      enabled: Boolean(autonomyEnabled?.checked),
      window_seconds: Math.max(60, Number(autonomyWindow?.value || 600)),
      max_messages_per_window: Math.max(1, Number(autonomyMaxMessages?.value || 3)),
      min_interval_seconds: minInterval,
      max_interval_seconds: maxInterval,
    },
    memory: {
      auto_extract_enabled: memoryAutoExtract?.checked ?? true,
      auto_extract_max_entries: Math.max(0, Number(memoryAutoMaxEntries?.value || 3)),
    },
    permissions: collectPermissionSettings(),
    persona: {
      name: personaName?.value || "",
      personality: personaPersonality?.value || "",
      speaking_style: personaSpeakingStyle?.value || "",
    },
  };
}

function modelSearchTerms() {
  return (modelSearch?.value || "")
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean);
}

function modelMatchesSearch(model, terms) {
  if (!terms.length) return true;
  const haystack = `${model?.name || ""} ${model?.kind || ""} ${model?.id || ""}`.toLowerCase();
  return terms.every((term) => haystack.includes(term));
}

function modelOptionLabel(model) {
  const name = model?.name || model?.id || "未命名模型";
  const kind = model?.kind ? ` (${model.kind})` : "";
  const live2d = model?.metadata?.live2d;
  const issue = live2d?.missing_assets?.length ? " / 缺资源" : "";
  return `${name}${kind}${issue}`;
}

function currentModel() {
  return state.models.find((model) => model.id === state.active_model_id) || state.models[0] || null;
}

function applyModelTheme(model) {
  const isDopamine = Boolean(model?.asset_root?.includes("多巴胺少女") || model?.name?.includes("Ayane"));
  document.body.dataset.avatarTheme = isDopamine ? "dopamine" : "default";
  if (!isDopamine || !model?.asset_root_url) {
    document.documentElement.style.removeProperty("--assistant-bg-image");
    return;
  }
  const backgroundUrl = new URL("../周边/Just%20Chatting/Static%20Complete%20Template.png", model.asset_root_url);
  document.documentElement.style.setProperty("--assistant-bg-image", `url("${backgroundUrl.href}")`);
}

function modelDiagnosticText(model) {
  if (!model) return "未发现模型";
  if (model.kind !== "live2d") return model.kind || "已加载";
  const live2d = model.metadata?.live2d || {};
  const missing = live2d.missing_assets?.length || 0;
  const expressions = live2d.expressions?.length || 0;
  return missing ? `Live2D 缺 ${missing} 项资源` : `Live2D / ${expressions} 表情`;
}

function renderModelOptions() {
  if (!modelSelect) return;
  const currentId = state.active_model_id || state.settings?.models?.default_id || "";
  const terms = modelSearchTerms();
  const models = Array.isArray(state.models) ? state.models : [];
  modelSelect.innerHTML = "";

  if (!models.length) {
    const option = document.createElement("option");
    option.textContent = "未发现模型";
    option.value = "";
    modelSelect.appendChild(option);
    return;
  }

  const filtered = models.filter((model) => modelMatchesSearch(model, terms));
  const currentInFiltered = filtered.some((model) => model.id === currentId);

  if (!filtered.length) {
    const option = document.createElement("option");
    option.textContent = "没有匹配模型";
    option.value = "";
    option.disabled = true;
    option.selected = true;
    modelSelect.appendChild(option);
    return;
  }

  if (terms.length && currentId && !currentInFiltered) {
    const option = document.createElement("option");
    option.textContent = "选择匹配模型";
    option.value = "";
    option.disabled = true;
    option.selected = true;
    modelSelect.appendChild(option);
  }

  for (const model of filtered) {
    const option = document.createElement("option");
    option.value = model.id || "";
    option.textContent = modelOptionLabel(model);
    option.selected = model.id === currentId;
    modelSelect.appendChild(option);
  }
}

function updateState(nextState) {
  const incoming = nextState && typeof nextState === "object" ? nextState : {};
  const previousProfileId = state.settings?.profile?.active_id || null;
  state = {
    settings: incoming.settings || {},
    models: Array.isArray(incoming.models) ? incoming.models : [],
    active_model_id: incoming.active_model_id || null,
    confirmations: Array.isArray(incoming.confirmations) ? incoming.confirmations : [],
  };
  const nextProfileId = state.settings?.profile?.active_id || null;
  if (previousProfileId && nextProfileId && previousProfileId !== nextProfileId) {
    activeAssistantMessage = null;
    if (messages) {
      messages.innerHTML = "";
    }
    if (miniBubbleText) {
      miniBubbleText.textContent = "";
    }
    hideMiniPopup();
  }
  const llm = state.settings?.llm;
  if (llm && providerText) {
    providerText.textContent = `${llm.provider_profile} / ${llm.model}`;
  }
  const persona = state.settings?.persona;
  if (persona) {
    if (personaStatus) personaStatus.textContent = persona.name || "已加载";
    if (chatTitle) chatTitle.textContent = persona.name || "桌面助理";
  }
  const memory = state.settings?.memory;
  if (memory && memoryStatus) {
    memoryStatus.textContent = memory.enabled
      ? `${memory.count || 0} 条 / 自动${memory.auto_extract_enabled === false ? "关" : "开"}`
      : "未启用";
  }
  const modelSources = state.settings?.models?.source_dirs || [];
  if (modelSourceStatus) {
    modelSourceStatus.textContent = `${modelSources.length} 个`;
  }
  const permissions = state.settings?.runtime_permissions || {};
  const permissionSummary = Object.entries(permissions)
    .map(([key, value]) => `${key}:${value}`)
    .join(" / ");
  if (permissionStatus) {
    permissionStatus.textContent = permissionSummary || "未知";
  }
  if (permissionPolicyStatus) {
    permissionPolicyStatus.textContent = summarizePermissionMap(state.settings?.permissions || {});
  }
  const confirmations = state.confirmations || [];
  if (confirmationStatus) {
    confirmationStatus.textContent = `${confirmations.length} 个`;
  }
  handleConfirmations(confirmations);
  const autonomy = state.settings?.autonomy || {};
  if (autonomyStatus) {
    autonomyStatus.textContent = autonomy.enabled
      ? `${autonomy.window_seconds || 0}s 内最多 ${autonomy.max_messages_per_window || 0} 条 / 随机 ${autonomy.min_interval_seconds || 0}-${autonomy.max_interval_seconds || 0}s`
      : "未启用";
  }
  const ui = state.settings?.ui || {};
  setPinnedControlState(ui.avatar_always_on_top !== false);
  const nextScale = clampScale(ui.avatar_scale || avatarTransform.scale || 1);
  if (Math.abs(nextScale - avatarTransform.scale) > 0.001) {
    avatarTransform.scale = nextScale;
    applyAvatarTransform();
  } else {
    syncScaleControl();
  }

  renderModelOptions();
  populateSettingsForm();
  const selected = currentModel();
  applyModelTheme(selected);
  if (isAvatarWindow) {
    renderer.render(selected);
  } else if (rendererStatus) {
    rendererStatus.textContent = modelDiagnosticText(selected);
  }
  if (isMainWindow && incoming.requested_view) {
    if (incoming.requested_view === "settings") showSettingsPanel();
    else showChatPopup();
  }
}

function handleConfirmations(confirmations) {
  if (!bridge || !isMainWindow) return;
  for (const item of confirmations) {
    if (!item?.id || handledConfirmations.has(item.id)) continue;
    handledConfirmations.add(item.id);
    const approved = window.confirm(`${item.action}\n${item.reason || "该操作需要确认。"}`);
    bridge.resolveConfirmation(item.id, approved, (payload) => {
      const result = parseJson(payload);
      if (!result.ok) {
        appendMessage("system", result.error || "确认处理失败");
        return;
      }
      const toolResult = result.tool_result;
      if (approved && toolResult) {
        const suffix = toolResult.ok ? "已执行" : toolResult.error || "执行失败";
        appendMessage("system", `确认已通过：${item.action}\n${suffix}`);
      } else {
        appendMessage("system", `确认已拒绝：${item.action}`);
      }
    });
  }
}

function sendUserMessage(text) {
  const cleaned = text.trim();
  if (!cleaned || !bridge) return;
  if (isAvatarWindow) {
    setBubbleText("我想一下。", "assistant");
    activeAssistantMessage = null;
    bridge.sendMessage(cleaned);
    return;
  }
  appendMessage("user", cleaned);
  activeAssistantMessage = appendMessage("assistant", "");
  bridge.sendMessage(cleaned);
}

function connectBridge() {
  if (!window.qt || !window.QWebChannel) {
    if (isAvatarWindow) {
      showMiniPopup();
      appendMessage("system", "未连接 Qt bridge，当前是前端预览模式。");
      renderer.startFallback("preview");
    } else {
      showChatPopup();
      appendMessage("system", "未连接 Qt bridge，当前是前端预览模式。");
    }
    return;
  }
  new QWebChannel(qt.webChannelTransport, (channel) => {
    bridge = channel.objects.assistantBridge;
    bridge.getInitialState((payload) => {
      updateState(parseJson(payload));
      applyAvatarTransform();
      restoreWindowPosition();
    });

    bridge.assistantDelta.connect((delta) => {
      if (isAvatarWindow) showMiniPopup({ focus: false });
      if (!activeAssistantMessage) {
        activeAssistantMessage = appendMessage("assistant", "");
      }
      if (activeAssistantMessage) {
        activeAssistantMessage.textContent += delta;
        const container = currentMessageContainer();
        if (container) {
          container.scrollTop = container.scrollHeight;
        }
      }
    });
    bridge.assistantDone.connect(() => {
      activeAssistantMessage = null;
      if (isAvatarWindow) scheduleBubbleAutoHide();
    });
    bridge.proactiveMessage.connect((text) => {
      if (isAvatarWindow) showMiniPopup({ focus: false });
      appendMessage("assistant", text);
      if (isAvatarWindow) scheduleBubbleAutoHide(12000);
    });
    bridge.busyChanged.connect((value) => setBusy(value));
    bridge.error.connect((text) => {
      if (isAvatarWindow) showMiniPopup({ focus: false });
      appendMessage("system", text);
      if (isAvatarWindow) scheduleBubbleAutoHide(14000);
    });
    bridge.stateChanged.connect((payload) => updateState(parseJson(payload, state)));
    bridge.contextChanged.connect((payload) => {
      const data = parseJson(payload);
      if (contextStatus) contextStatus.textContent = data.frontmost_app || "已刷新";
      if (contextPreview) contextPreview.textContent = JSON.stringify(data, null, 2);
    });
    bridge.openView.connect((view) => {
      if (!isMainWindow) return;
      if (view === "settings") showSettingsPanel();
      else showChatPopup();
    });
  });
}

function bindWindowDrag(handle) {
  if (!handle) return;
  let dragState = null;
  handle.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button, input, textarea, select")) return;
    dragState = {
      pointerId: event.pointerId,
      lastX: event.screenX,
      lastY: event.screenY,
      moved: false,
    };
    handle.setPointerCapture(event.pointerId);
  });
  handle.addEventListener("pointermove", (event) => {
    if (!dragState || dragState.pointerId !== event.pointerId) return;
    const dx = event.screenX - dragState.lastX;
    const dy = event.screenY - dragState.lastY;
    dragState.lastX = event.screenX;
    dragState.lastY = event.screenY;
    if (Math.abs(dx) + Math.abs(dy) > 0) dragState.moved = true;
    if (bridge?.moveWindowBy && (dx || dy)) {
      bridge.moveWindowBy(Math.round(dx), Math.round(dy), (payload) => {
        storeWindowFrame(parseJson(payload));
      });
    }
  });
  handle.addEventListener("pointerup", (event) => {
    if (dragState?.pointerId === event.pointerId) {
      if (dragState.moved) persistWindowFrame();
      dragState = null;
    }
  });
}

let avatarDragState = null;
avatarHit?.addEventListener("pointerdown", (event) => {
  if (!isAvatarWindow) return;
  avatarDragState = {
    pointerId: event.pointerId,
    startX: event.screenX,
    startY: event.screenY,
    lastX: event.screenX,
    lastY: event.screenY,
    moved: false,
  };
  avatarHit.setPointerCapture(event.pointerId);
});

avatarHit?.addEventListener("pointermove", (event) => {
  if (!avatarDragState || avatarDragState.pointerId !== event.pointerId) return;
  const totalDx = event.screenX - avatarDragState.startX;
  const totalDy = event.screenY - avatarDragState.startY;
  const dx = event.screenX - avatarDragState.lastX;
  const dy = event.screenY - avatarDragState.lastY;
  if (Math.abs(totalDx) + Math.abs(totalDy) > 4) {
    avatarDragState.moved = true;
  }
  avatarDragState.lastX = event.screenX;
  avatarDragState.lastY = event.screenY;
  if (bridge?.moveWindowBy && (dx || dy)) {
    bridge.moveWindowBy(Math.round(dx), Math.round(dy), (payload) => {
      storeWindowFrame(parseJson(payload));
    });
  }
});

avatarHit?.addEventListener("pointerup", (event) => {
  if (avatarDragState?.pointerId === event.pointerId) {
    if (avatarDragState.moved) {
      event.preventDefault();
      event.stopPropagation();
      persistWindowFrame();
    } else {
      showMiniPopup({ focus: true });
    }
    avatarDragState = null;
  }
});

avatarHit?.addEventListener("wheel", (event) => {
  if (!isAvatarWindow) return;
  event.preventDefault();
  const delta = event.deltaY < 0 ? 0.06 : -0.06;
  avatarTransform.scale = clampScale(avatarTransform.scale + delta);
  applyAvatarTransform();
  queueSettingsSave({ ui: { avatar_scale: avatarTransform.scale } });
});

let resizeState = null;
mainResizeGrip?.addEventListener("pointerdown", (event) => {
  if (!isMainWindow) return;
  resizeState = {
    pointerId: event.pointerId,
    startX: event.screenX,
    startY: event.screenY,
    startWidth: currentWindowFrame?.width || window.innerWidth,
    startHeight: currentWindowFrame?.height || window.innerHeight,
  };
  mainResizeGrip.setPointerCapture(event.pointerId);
});

mainResizeGrip?.addEventListener("pointermove", (event) => {
  if (!resizeState || resizeState.pointerId !== event.pointerId) return;
  const width = resizeState.startWidth + event.screenX - resizeState.startX;
  const height = resizeState.startHeight + event.screenY - resizeState.startY;
  bridge?.resizeWindow?.(Math.round(width), Math.round(height), (payload) => {
    storeWindowFrame(parseJson(payload));
  });
});

mainResizeGrip?.addEventListener("pointerup", (event) => {
  if (resizeState?.pointerId === event.pointerId) {
    persistWindowFrame();
    resizeState = null;
  }
});

openMainFromMini?.addEventListener("click", () => {
  bridge?.openMainWindow?.("chat");
});

toolbarChat?.addEventListener("click", () => {
  bridge?.openMainWindow?.("chat");
});

toolbarSettings?.addEventListener("click", () => {
  bridge?.openMainWindow?.("settings");
});

toolbarMinimize?.addEventListener("click", () => {
  hideMiniPopup();
});

toolbarPin?.addEventListener("click", () => {
  const current = state.settings?.ui?.avatar_always_on_top !== false;
  savePinnedState(!current);
});

closeChat?.addEventListener("click", () => {
  if (isMainWindow) bridge?.hideMainWindow?.();
});

openPanel?.addEventListener("click", () => {
  showSettingsPanel();
});

openChat?.addEventListener("click", () => {
  showChatPopup();
});

closePanel?.addEventListener("click", () => {
  if (isMainWindow) bridge?.hideMainWindow?.();
});

chatForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = "";
  sendUserMessage(text);
});

miniForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = miniInput.value.trim();
  if (!text) return;
  miniInput.value = "";
  sendUserMessage(text);
});

miniInput?.addEventListener("focus", () => {
  clearBubbleHideTimer();
});

miniInput?.addEventListener("blur", () => {
  if (!miniInput.value.trim()) {
    scheduleBubbleAutoHide();
  }
});

modelSearch?.addEventListener("input", () => {
  renderModelOptions();
});

profileSelect?.addEventListener("change", () => {
  if (!bridge || !profileSelect.value) return;
  bridge.switchProfile(profileSelect.value, (payload) => {
    handleProfileResponse(payload, "已切换小人存档");
  });
});

createProfile?.addEventListener("click", () => {
  if (!bridge?.createProfile) return;
  const name = window.prompt("新建小人存档名称", profileName?.value || "新小人");
  if (!name?.trim()) return;
  bridge.createProfile(name.trim(), (payload) => {
    handleProfileResponse(payload, "已新建并切换存档");
  });
});

renameProfile?.addEventListener("click", () => {
  const activeId = state.settings?.profile?.active_id;
  const name = profileName?.value.trim();
  if (!bridge?.renameProfile || !activeId || !name) return;
  bridge.renameProfile(activeId, name, (payload) => {
    handleProfileResponse(payload, "存档已重命名");
  });
});

deleteProfile?.addEventListener("click", () => {
  const activeId = state.settings?.profile?.active_id;
  const profiles = state.settings?.profile?.profiles || [];
  if (!bridge?.deleteProfile || !activeId || profiles.length <= 1) return;
  const activeName = state.settings?.profile?.name || activeId;
  if (!window.confirm(`删除小人存档「${activeName}」？本地记忆和对话记录也会删除。`)) return;
  bridge.deleteProfile(activeId, (payload) => {
    handleProfileResponse(payload, "存档已删除");
  });
});

modelSelect?.addEventListener("change", () => {
  if (!bridge || !modelSelect.value) return;
  bridge.setActiveModel(modelSelect.value, (payload) => {
    const result = parseJson(payload);
    if (result.state) updateState(result.state);
    setSettingsStatus(result.ok ? "模型选择已保存" : result.error || "模型保存失败", !result.ok);
  });
});

avatarScaleInput?.addEventListener("input", () => {
  avatarTransform.scale = clampScale(avatarScaleInput.value);
  syncScaleControl();
  queueSettingsSave({ ui: { avatar_scale: avatarTransform.scale } });
});

avatarAlwaysOnTop?.addEventListener("change", () => {
  savePinnedState(Boolean(avatarAlwaysOnTop.checked));
});

saveSettings?.addEventListener("click", () => {
  saveSettingsPayload(collectSettingsForm(), { showStatus: true });
});

refreshContext?.addEventListener("click", () => {
  if (!bridge) return;
  bridge.refreshContext((payload) => {
    const data = parseJson(payload);
    if (contextStatus) contextStatus.textContent = data.frontmost_app || "已刷新";
    if (contextPreview) contextPreview.textContent = JSON.stringify(data, null, 2);
  });
});

messageInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    chatForm.requestSubmit();
  }
});

miniInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
    miniForm.requestSubmit();
  }
});

for (const handle of document.querySelectorAll("[data-window-drag]")) {
  bindWindowDrag(handle);
}

if (isMainWindow) {
  showChatPopup();
}
applyAvatarTransform();
connectBridge();
