"""Xia Director language instruction — Indonesian (Bahasa Indonesia).

Used when the UI language / ``DRAMACLAW_UI_LANGUAGE`` is ``id``. The
frontend UI itself has no ``id`` locale (supported UI languages are
zh / en / vi / pt), so ``id`` is opt-in: send ``ui_language: "id"`` in the
chat context, or set ``DRAMACLAW_UI_LANGUAGE=id`` on the api service.

Design note: dialogue and story prose are Indonesian, but visual
generation prompts (``visual_description`` and other image / video prompt
fields) stay in English — the image / video models are prompted in
English upstream, and translating those fields into Indonesian degrades
generation quality. Character and location names are kept verbatim.
"""

from __future__ import annotations

DIRECTOR_LANGUAGE_INSTRUCTION = """[DRAMACLAW_LANGUAGE]
director_language: id
- Reply to the user in Bahasa Indonesia.
- Write every user-visible prose field (chat replies, plans, story scripts,
  character settings, scene settings, node titles and summaries) in
  Bahasa Indonesia. Dialogue in the script must be in Bahasa Indonesia.
- Keep every supplied character and location name verbatim; never
  translate, romanize, or rewrite a name.
- Visual generation prompts (image / video prompt fields such as
  visual_description) must stay in English, because the image / video
  generators are prompted in English. Do not translate those fields into
  Indonesian.
- If the user shares a public video link (YouTube / TikTok / Instagram)
  and asks for an analysis, use the dramaclaw_post tool on
  /api/v1/projects/{project}/freezone/analyze-video-reference with
  video_url, mode (duplicate / reference / idea), checklist and
  extra_notes, then poll the returned task_key for the result. The
  backend downloads the video and analyses it; you only receive text.
- Jika pengguna membagikan link artikel publik atau menempel teks artikel
  dan meminta analisis, gunakan dramaclaw_post pada
  /api/v1/projects/{project}/freezone/analyze-article-reference dengan
  article_url (atau article_text), mode (duplicate / reference / idea),
  checklist dan extra_notes, lalu poll task_key yang dikembalikan. Backend
  mengambil artikel dan menganalisisnya dengan model teks yang sudah
  dikonfigurasi; kamu hanya menerima teks. Jika extra_notes berisi premis
  cerita pengguna sendiri, terapkan artikel itu pada cerita TERSEBUT,
  jangan menceritakan ulang isi artikel.
[/DRAMACLAW_LANGUAGE]"""

# Indonesian counterpart of rule 6 of FREEZONE_STORY_SCRIPT_SYSTEM_PROMPT
# in freezone/text_node.py. Story prose is Indonesian; the visual prompt
# fields keep English (see the director instruction above).
STORY_SCRIPT_LANGUAGE_RULE = (
    "Keep all story and dialogue fields in Bahasa Indonesia, and keep "
    "visual_description / shot prompt fields in English, except technical "
    "tokens when naturally needed."
)

# Indonesian display titles of the deterministic standard-planner workflow
# items (see ``lang/zh.py`` for the layout contract). Visual terms such as
# Frame / Video stay in English, matching the id pack's rule that visual
# generation prompt fields stay English.
WORKFLOW_ITEM_TITLES = {
    "outline": "Perencanaan Konten",
    "ad_outline": "Garis Besar Kreatif Iklan",
    "product_anchor": "Anchor Visual Produk",
    "character_setup": "Pengaturan Karakter",
    "scene_setup": "Pengaturan Adegan",
    "prop_setup": "Pengaturan Properti",
    "character_image": "Gambar Identitas Karakter",
    "scene_image": "Gambar Referensi Adegan",
    "prop_image": "Gambar Referensi Properti",
    "shot_design_suffix": " Desain Shot",
    "first_frame_suffix": " Frame Pertama",
    "frame_suffix": " Frame",
    "video_suffix": " Video",
    "narration_suffix": " Narasi",
    "background_music": "Musik Latar",
    "outline_part": "Bagian {index}",
    "outline_narration_label": "Narasi: ",
    "outline_facts_header": "Fakta dan narasi tiap bagian (harus dipertahankan selengkapnya):",
    "deferred_narration_prompt": (
        "Hanya bacakan narasi, voiceover, dialog, atau speech_text dari "
        "output desain shot di atas. Jangan bacakan catatan produksi."
    ),
    "final_compose": "Komposisi Akhir",
    "final_compose_description": (
        "Gabungkan klip video, musik, dan narasi ke timeline "
        "untuk hasil akhir."
    ),
    "workflow_input": "Permintaan Pengguna / Materi Input",
}
