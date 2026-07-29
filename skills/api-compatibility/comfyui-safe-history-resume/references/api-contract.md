# ComfyUI history and media contract

The history endpoint normally returns a dictionary keyed by Prompt ID:

```json
{
  "PROMPT_ID": {
    "outputs": {
      "NODE_ID": {
        "images": [
          {
            "filename": "shot01_00001_.png",
            "subfolder": "flower_scene",
            "type": "output"
          }
        ]
      }
    },
    "status": {
      "completed": true,
      "status_str": "success",
      "messages": []
    }
  }
}
```

Do not assume a fixed output node ID. Do not assume media is directly under `history["images"]`.

Download with:

```text
GET /view?filename=<filename>&subfolder=<subfolder>&type=<type>
```

A successful status with empty `outputs` is `completed_without_media`, not a valid generated result and not proof of OOM.
