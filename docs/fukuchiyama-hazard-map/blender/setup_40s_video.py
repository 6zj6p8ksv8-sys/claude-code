# 中間報告会用 40秒動画のセットアップ（Blender の Scripting タブで実行）
#
# やること
#   1. 水面オブジェクトの Geometry Nodes 入力「Water Level」に、40秒分のキーフレームを打つ
#      （前に打ったこの入力のキーフレームは消してから打ち直す）
#   2. 30fps・1〜1200フレーム・1280x720・EEVEE・MP4(H.264) に設定する
#   3. （任意）カメラのキーフレームを 1〜1200 フレームに伸び縮みさせる
#
# 使い方
#   - 下の「設定」を自分のシーンに合わせて書き換え、Scripting タブで「スクリプト実行」（Alt+P）
#   - 先に .blend を保存しておくこと（失敗しても Ctrl+Z で戻せるが、念のため）
#   - Blender 4.1〜4.5 で動く想定

import bpy

# ===== 設定 =====================================================
WATER_OBJECT = "Water"        # 水面オブジェクトの名前（アウトライナーの名前）
INPUT_NAME = "Water Level"    # Geometry Nodes の入力の名前

# BASE：水面がちょうど「市民病院の地面」に触れるときの Water Level の値。
#   スライダーを動かして、病院の位置で水がちょうど地面に触れる値を探し、ここに書く。
#   （地形の標高を調べなくても、これで「病院の地面から何m」として水位を決められる）
BASE = 0.0

# 浸水深（病院の地面から何mか）のキー。(フレーム, 浸水深m)
# ハザードマップ（想定最大規模）：市民病院周辺 内水 〜3.0m未満／外水 5.0〜10.0m未満
# → 区分の上限付近の値を目安に 2.9m・9.5m とした（動画内でそう断る）
KEYS = [
    (1,    0.0),   # 0秒   降り始め
    (240,  2.9),   # 8秒   内水ピーク（排水が追いつかない）
    (420,  2.9),   # 14秒  内水のまま停滞（由良川の水位が上がり排水できない）
    (1050, 9.5),   # 35秒  外水ピーク
    (1200, 9.5),   # 40秒  高い水位が続く（浸水が長く続くことを表す）
]

FPS = 30
FRAME_END = 1200
RES_X, RES_Y = 1280, 720
RENDER_SAMPLES = 32                       # 重ければ 16 に
OUTPUT = "//render/fukuchiyama_40s_"      # .blend と同じ場所の render フォルダに出力

RETIME_CAMERA = False   # True にすると、カメラのキーフレームを 1〜FRAME_END に合わせて伸ばす
CAMERA_OBJECT = ""      # 空ならシーンのアクティブカメラ
# ================================================================


def find_modifier_and_identifier(obj, input_name):
    for mod in obj.modifiers:
        if mod.type != 'NODES' or mod.node_group is None:
            continue
        ng = mod.node_group
        if hasattr(ng, "interface"):  # Blender 4.0 以降
            for item in ng.interface.items_tree:
                if (getattr(item, "item_type", "") == 'SOCKET'
                        and item.in_out == 'INPUT' and item.name == input_name):
                    return mod, item.identifier
        else:  # Blender 3.x
            for sock in ng.inputs:
                if sock.name == input_name:
                    return mod, sock.identifier
    return None, None


def action_fcurves(obj):
    ad = obj.animation_data
    if ad is None or ad.action is None:
        return []
    action = ad.action
    try:
        return list(action.fcurves)
    except AttributeError:  # レイヤー型アクション（新しい Blender）
        from bpy_extras import anim_utils
        bag = anim_utils.action_get_channelbag_for_slot(action, ad.action_slot)
        return list(bag.fcurves) if bag else []


def remove_fcurve(obj, data_path):
    ad = obj.animation_data
    if ad is None or ad.action is None:
        return
    for fc in action_fcurves(obj):
        if fc.data_path == data_path:
            try:
                ad.action.fcurves.remove(fc)
            except AttributeError:
                from bpy_extras import anim_utils
                bag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
                bag.fcurves.remove(fc)


def set_water_keys():
    obj = bpy.data.objects.get(WATER_OBJECT)
    if obj is None:
        raise RuntimeError(f"オブジェクト「{WATER_OBJECT}」が見つかりません。WATER_OBJECT を直してください。")
    mod, ident = find_modifier_and_identifier(obj, INPUT_NAME)
    if mod is None:
        raise RuntimeError(f"「{WATER_OBJECT}」に、入力「{INPUT_NAME}」を持つ Geometry Nodes モディファイアがありません。")

    data_path = f'modifiers["{mod.name}"]["{ident}"]'
    remove_fcurve(obj, data_path)
    for frame, depth in KEYS:
        mod[ident] = BASE + depth
        obj.keyframe_insert(data_path=data_path, frame=frame)
    for fc in action_fcurves(obj):
        if fc.data_path == data_path:
            for kp in fc.keyframe_points:
                kp.interpolation = 'LINEAR'
    obj.update_tag()
    print(f"水位キー: {len(KEYS)}個（{mod.name} / {INPUT_NAME}、BASE={BASE}）")


def retime_camera(scene):
    cam = bpy.data.objects.get(CAMERA_OBJECT) if CAMERA_OBJECT else scene.camera
    if cam is None or cam.animation_data is None or cam.animation_data.action is None:
        print("カメラのキーフレームが見つからないので、伸び縮みは行いませんでした。")
        return
    fcs = action_fcurves(cam)
    frames = [kp.co.x for fc in fcs for kp in fc.keyframe_points]
    if len(frames) < 2:
        return
    lo, hi = min(frames), max(frames)
    if hi == lo:
        return
    scale = (FRAME_END - 1) / (hi - lo)
    for fc in fcs:
        for kp in fc.keyframe_points:
            for attr in ("co", "handle_left", "handle_right"):
                p = getattr(kp, attr)
                p.x = 1 + (p.x - lo) * scale
        fc.update()
    print(f"カメラ「{cam.name}」のキーを {lo:.0f}〜{hi:.0f} → 1〜{FRAME_END} に伸ばしました。")


def set_render(scene):
    scene.render.fps = FPS
    scene.render.fps_base = 1.0
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.resolution_x = RES_X
    scene.render.resolution_y = RES_Y
    scene.render.resolution_percentage = 100

    engines = {e.identifier for e in scene.render.bl_rna.properties["engine"].enum_items}
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in engines else "BLENDER_EEVEE"
    try:
        scene.eevee.taa_render_samples = RENDER_SAMPLES
    except AttributeError:
        pass

    img = scene.render.image_settings
    if hasattr(img, "media_type"):  # 新しい Blender では先に「動画」を選ぶ
        img.media_type = 'VIDEO'
    img.file_format = 'FFMPEG'
    ff = scene.render.ffmpeg
    ff.format = 'MPEG4'
    ff.codec = 'H264'
    ff.constant_rate_factor = 'HIGH'
    ff.audio_codec = 'NONE'
    scene.render.filepath = OUTPUT
    print(f"描画: {scene.render.engine}, {RES_X}x{RES_Y}, {FPS}fps, 1〜{FRAME_END}フレーム, 出力 {OUTPUT}")


scene = bpy.context.scene
set_water_keys()
set_render(scene)
if RETIME_CAMERA:
    retime_camera(scene)
scene.frame_set(1)
print("完了。タイムラインを再生して水位の動きを確認してください。")
