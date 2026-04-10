import os
import sys
import logging
import tempfile
from typing import Any, Dict, List
from pathlib import Path

logger = logging.getLogger(__name__)


def _atomic_save_pptx(prs: Any, final_path: str) -> None:
    """
    PRD §7.3 Tool 11: 原子写入 PPTX 文件。
    
    写入到同目录临时文件，再 os.rename 原子替换，防止并发读到中间态文件。
    Unix 用 fcntl.flock 文件锁；Windows 无 fcntl 则直接写。
    """
    final = Path(final_path)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=final.parent, suffix=".tmp.pptx")
    try:
        if sys.platform != "win32":
            import fcntl
            with open(tmp_path, "wb") as fp:
                fcntl.flock(fp, fcntl.LOCK_EX)
                prs.save(fp)
                fcntl.flock(fp, fcntl.LOCK_UN)
        else:
            # Windows: no fcntl — close the fd first, then save
            os.close(tmp_fd)
            tmp_fd = -1
            prs.save(tmp_path)
        os.rename(tmp_path, final_path)
        logger.info("pptx_atomic_write_ok", extra={"path": final_path})
    except Exception:
        # Clean up temp on failure
        try:
            if tmp_fd >= 0:
                os.close(tmp_fd)
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    finally:
        # Ensure fd closed (may already be closed)
        if tmp_fd >= 0:
            try:
                os.close(tmp_fd)
            except OSError:
                pass


def draw_bounding_boxes(image_path: str, boxes: List[Dict], out_path: str) -> bool:
    """
    Draws red bounding boxes on an image based on AI detections.
    Requires Pillow.
    boxes format: [{"box_2d": [x1, y1, x2, y2], "label": "..."}]
    """
    try:
        from PIL import Image, ImageDraw  # type: ignore
        img = Image.open(image_path)
        draw = ImageDraw.Draw(img)
        
        for box in boxes:
            coords = box.get("box_2d")
            if coords and len(coords) == 4:
                draw.rectangle(coords, outline="red", width=3)
                label = box.get("label")
                if label:
                    draw.text((coords[0], max(0, coords[1] - 15)), label, fill="red")
        
        img.save(out_path)
        return True
    except Exception as e:
        logger.error(f"Failed to draw bounding box on {image_path}: {e}")
        return False

def generate_report_pptx(task_id: str, items: List[Dict], receipts: dict, template_id: str = "default") -> str:
    """
    Core PPTX renderer generating the full report and applying bounding boxes.
    Outputs to FILE_STORAGE_ROOT/aicopilot/<task_id>/
    PRD §7.3 Tool 11: uses atomic write (temp file + os.rename) to prevent dirty reads.
    """
    out_dir = Path(os.environ.get("FILE_STORAGE_ROOT", "/data")) / "aicopilot" / str(task_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    pptx_path = str(out_dir / f"output_{template_id}.pptx")
    
    try:
        from pptx import Presentation  # type: ignore
        from pptx.util import Inches, Pt  # type: ignore
        from pptx.enum.shapes import PP_PLACEHOLDER
    except Exception as e:
        raise RuntimeError("Missing python-pptx dependency") from e

    prs = Presentation()
    
    # Slide 1: Cover
    title_slide = prs.slides.add_slide(prs.slide_layouts[0])
    title_slide.shapes.title.text = "活动项目智能结案报告"
    title_slide.placeholders[1].text = f"由 AI Copilot 自动生成 | 任务 ID: {task_id}"

    # Slide 2: Material Execution List
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # Title only
    slide.shapes.title.text = "物料执行清单与照片证明"
    tx = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9.0), Inches(5.5)).text_frame
    tx.word_wrap = True
    
    for it in items[:15]:  # Show top 15 materials for brevity
        p = tx.add_paragraph()
        name = it.get('name', '')
        target = it.get('target_qty', 0)
        actual = it.get('actual_qty', target)
        status = "✅ 达标" if actual >= target else "⚠️ 异常"
        p.text = f"• {name} | 目标: {target} | 实际: {actual} | 状态: {status}"
        p.font.size = Pt(14)
        
    # Slide 2.x: Images for Material Execution
    pic_layout = None
    pic_placeholder_idx = -1
    text_placeholder_idx = -1
    
    for layout in prs.slide_layouts:
        has_pic = False
        p_idx = -1
        t_idx = -1
        for shape in layout.placeholders:
            if shape.placeholder_format.type == PP_PLACEHOLDER.PICTURE:
                has_pic = True
                p_idx = shape.placeholder_format.idx
            elif shape.placeholder_format.type in (PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT, PP_PLACEHOLDER.TITLE):
                t_idx = shape.placeholder_format.idx
        if has_pic:
            pic_layout = layout
            pic_placeholder_idx = p_idx
            text_placeholder_idx = t_idx
            break

    for it in items[:15]:
        img_path = it.get('design_image_path')
        if not img_path or not os.path.exists(img_path):
            continue
            
        name = it.get('name', '')
        target = it.get('target_qty', 0)
        actual = it.get('actual_qty', target)
        status = "✅ 达标" if actual >= target else "⚠️ 异常"
        info_text = f"名称: {name}\n目标数量: {target}\n实际数量: {actual}\n状态: {status}"

        if pic_layout:
            slide_pic = prs.slides.add_slide(pic_layout)
            for shape in slide_pic.placeholders:
                if shape.placeholder_format.idx == pic_placeholder_idx:
                    try:
                        shape.insert_picture(img_path)
                    except Exception as e:
                        logger.error(f"Failed to insert picture placeholder for {img_path}: {e}")
                elif shape.placeholder_format.idx == text_placeholder_idx or shape.placeholder_format.type == PP_PLACEHOLDER.TITLE:
                    shape.text = f"证明照片: {name}" if shape.placeholder_format.type == PP_PLACEHOLDER.TITLE else info_text
        else:
            slide_pic = prs.slides.add_slide(prs.slide_layouts[5])  # Title only
            slide_pic.shapes.title.text = f"物料执行证明: {name}"
            tx_pic = slide_pic.shapes.add_textbox(Inches(0.5), Inches(2.0), Inches(3.5), Inches(4.0)).text_frame
            tx_pic.text = info_text
            try:
                # Add adaptive picture to right side
                slide_pic.shapes.add_picture(img_path, Inches(4.5), Inches(1.5), width=Inches(5.0))
            except Exception as e:
                logger.error(f"Failed to add picture {img_path}: {e}")

    # Slide 3: Finance Matches
    slide2 = prs.slides.add_slide(prs.slide_layouts[5])
    slide2.shapes.title.text = "财务凭据匹配摘要"
    
    matches = receipts.get("matches", [])
    unmatched = receipts.get("unmatched", [])
    
    tx2 = slide2.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9.0), Inches(5.5)).text_frame
    tx2.word_wrap = True
    
    p = tx2.add_paragraph()
    p.text = f"匹配成功：{len(matches)} 笔 | 异常未匹配：{len(unmatched)} 笔"
    p.font.size = Pt(16)
    p.font.bold = True
    
    tx2.add_paragraph().text = ""
    
    for m in matches[:10]:
        p = tx2.add_paragraph()
        pmt = m.get("payment", {})
        inv = m.get("invoice", {})
        amount = pmt.get("amount") or inv.get("amount")
        p.text = f"[匹配成功] 交易: {pmt.get('date')} ￥{amount} <=> 发票号: {inv.get('invoice_no')}"
        p.font.size = Pt(12)

    for u in unmatched[:10]:
        p = tx2.add_paragraph()
        p.text = f"[待人工确认] 未匹配资产 | 类型: {u.get('type')} ￥{u.get('amount')}"
        p.font.size = Pt(12)

    # PRD §7.3 Tool 11: 原子写入，防止并发读到中间态
    _atomic_save_pptx(prs, pptx_path)
    return pptx_path

