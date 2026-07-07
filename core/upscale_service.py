"""图像放大服务 —— 与 Qt 解耦，复用 plugins.upscale 的 ONNX 推理逻辑。

以普通线程运行，通过 emit(event_dict) 回调推送日志/进度/完成事件，支持取消。
"""
import os
import threading


def process_tiled(sess, input_name, output_name, rgb_image, is_cancelled=None):
    """分块 ONNX 推理（从 plugins.upscale 移植，与 Qt 解耦）。

    rgb_image: H x W x 3 float32 in [0,1]；返回 (H*4)x(W*4)x3 float32 in [0,1]。
    """
    import numpy as np
    from plugins import upscale as up

    h, w = rgb_image.shape[:2]
    tile = up.TILE_SIZE
    overlap = up.TILE_OVERLAP
    stride = tile - overlap

    pad_h = max(0, tile - h)
    pad_w = max(0, tile - w)
    padded = np.pad(rgb_image, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')
    ph, pw = padded.shape[:2]

    out_h, out_w = h * up.SCALE_FACTOR, w * up.SCALE_FACTOR
    out_tile = tile * up.SCALE_FACTOR

    result = np.zeros((ph * up.SCALE_FACTOR, pw * up.SCALE_FACTOR, 3), dtype=np.float32)
    weight = np.zeros((ph * up.SCALE_FACTOR, pw * up.SCALE_FACTOR, 3), dtype=np.float32)

    mask = np.ones((out_tile, out_tile, 1), dtype=np.float32)
    fade = overlap * up.SCALE_FACTOR
    if fade > 0:
        for i in range(fade):
            alpha = (i + 1) / (fade + 1)
            mask[i, :, 0] *= alpha
            mask[-1 - i, :, 0] *= alpha
            mask[:, i, 0] *= alpha
            mask[:, -1 - i, 0] *= alpha

    for y in range(0, ph, stride):
        for x in range(0, pw, stride):
            if is_cancelled and is_cancelled():
                return result[:out_h, :out_w]
            y0 = min(y, ph - tile)
            x0 = min(x, pw - tile)
            patch = padded[y0:y0 + tile, x0:x0 + tile]
            patch_nchw = np.transpose(patch, (2, 0, 1))[np.newaxis, :, :, :]
            out = sess.run([output_name], {input_name: patch_nchw})
            out_patch = np.transpose(out[0][0], (1, 2, 0))
            out_y0 = y0 * up.SCALE_FACTOR
            out_x0 = x0 * up.SCALE_FACTOR
            result[out_y0:out_y0 + out_tile, out_x0:out_x0 + out_tile] += out_patch * mask
            weight[out_y0:out_y0 + out_tile, out_x0:out_x0 + out_tile] += mask

    weight[weight < 1e-6] = 1.0
    result /= weight
    return result[:out_h, :out_w]


class UpscaleTask:
    def __init__(self, input_dir: str, output_dir: str, output_format: str = "png"):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.output_format = output_format
        self._cancel = threading.Event()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def stop(self):
        self._cancel.set()

    def start(self, emit):
        t = threading.Thread(target=self._worker, args=(emit,), daemon=True)
        t.start()

    def _worker(self, emit):
        try:
            emit({"type": "log", "msg": "正在加载 AI 超分模型..."})
            from plugins import upscale as up
            import numpy as np
            import cv2

            images = up.scan_images(self.input_dir)
            total = len(images)
            if total == 0:
                emit({"type": "log", "msg": "未找到可处理的图片。"})
                emit({"type": "done", "success": False})
                return
            emit({"type": "log", "msg": f"发现 {total} 张图片，输出格式 {self.output_format}"})

            model_path = up.find_or_download_model(lambda m: emit({"type": "log", "msg": m}))
            if not model_path:
                emit({"type": "log", "msg": "无法获取模型，请检查网络。"})
                emit({"type": "done", "success": False})
                return

            import onnxruntime as ort
            sess = ort.InferenceSession(model_path, providers=['CPUExecutionProvider'])
            inp = sess.get_inputs()[0]
            out = sess.get_outputs()[0]
            emit({"type": "log", "msg": f"模型已加载 (Real-ESRGAN, {up.SCALE_FACTOR}x 放大)"})

            os.makedirs(self.output_dir, exist_ok=True)
            emit({"type": "progress", "current": 0, "total": total})

            for idx, img_path in enumerate(images):
                if self.cancelled:
                    emit({"type": "log", "msg": "任务已取消。"})
                    emit({"type": "done", "success": False})
                    return
                fname = os.path.basename(img_path)
                emit({"type": "log", "msg": f"[{idx + 1}/{total}] {fname}"})
                try:
                    raw = np.fromfile(img_path, dtype=np.uint8)
                    if len(raw) == 0:
                        emit({"type": "log", "msg": "  空文件，跳过"})
                        continue
                    img = cv2.imdecode(raw, cv2.IMREAD_COLOR)
                    if img is None:
                        emit({"type": "log", "msg": "  解码失败，跳过"})
                        continue
                    h, w = img.shape[:2]
                    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
                    result_rgb = process_tiled(sess, inp.name, out.name, img_rgb, lambda: self.cancelled)
                    new_h, new_w = h * up.SCALE_FACTOR, w * up.SCALE_FACTOR
                    result_rgb = np.clip(result_rgb * 255.0, 0, 255).astype(np.uint8)
                    result_bgr = cv2.cvtColor(result_rgb, cv2.COLOR_RGB2BGR)
                    out_path = os.path.join(self.output_dir, fname)
                    if self.output_format == "jpg":
                        ok, buf = cv2.imencode('.jpg', result_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    elif self.output_format == "webp":
                        ok, buf = cv2.imencode('.webp', result_bgr, [cv2.IMWRITE_WEBP_QUALITY, 95])
                    else:
                        ok, buf = cv2.imencode('.png', result_bgr, [cv2.IMWRITE_PNG_COMPRESSION, 3])
                    if ok:
                        buf.tofile(out_path)
                        emit({"type": "log", "msg": f"  OK  {w}x{h} -> {new_w}x{new_h}"})
                    else:
                        emit({"type": "log", "msg": "  编码失败"})
                except Exception as e:
                    emit({"type": "log", "msg": f"  FAIL {e}"})
                emit({"type": "progress", "current": idx + 1, "total": total})

            emit({"type": "log", "msg": f"全部完成！共 {total} 张，输出至 {self.output_dir}"})
            emit({"type": "done", "success": True})
        except Exception as e:
            emit({"type": "log", "msg": f"系统错误: {e}"})
            emit({"type": "done", "success": False})
