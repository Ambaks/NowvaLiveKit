/* Part copy, keyed by glTF node id. Ported from part-explorer/src/data/parts.json.
   A part with no entry here still renders and is still clickable - it just
   shows its raw node name and an empty panel. */

export interface PartContent {
  displayName?: string;
  category?: string;
  role?: string;
  specs?: [string, string][];
}

export const partContent: Record<string, PartContent> = {
  STEEL_BASE: {
    "displayName": "Core chassis",
    "category": "intelligence",
    "role": "The load-bearing spine of the rack, and where Nowva actually lives. Three cameras sight you at once — one head-on from the screen, one from each upright at forty-five degrees — and the overlap is what turns flat video into a true three-dimensional read of how you move. Behind them sits NOWVABRAIN, the compute block that runs every model on the machine itself. Your training never leaves the room.",
    "specs": [
      [
        "Vision",
        "Three cameras — front and two 45° views"
      ],
      [
        "Reconstruction",
        "3D triangulation from overlapping views"
      ],
      [
        "Compute",
        "NOWVABRAIN onboard GPU"
      ],
      [
        "Processing",
        "Fully local — no cloud, no upload"
      ],
      [
        "Footprint",
        "1.21 × 1.07 m"
      ],
      [
        "Height",
        "1.70 m"
      ]
    ]
  },
  NOWVABRAIN: {
    "displayName": "NOWVABRAIN",
    "category": "intelligence",
    "role": "The compute block. Pose estimation, biomechanics and coaching all run here, on the machine, in real time — no round trip to a server, no lag between the rep and the cue, and no footage of you leaving the building.",
    "specs": [
      [
        "Inference",
        "On-device GPU"
      ],
      [
        "Latency",
        "Real-time, rep by rep"
      ],
      [
        "Privacy",
        "Nothing leaves the device"
      ]
    ]
  },
  LUXURY_CASING: {
    "displayName": "Luxury shell",
    "category": "enclosure",
    "role": "A single seamless envelope wrapping the entire rack, formed in a high-grade polymer with a deep, soft-touch finish — closer to furniture than to gym equipment. It is also how Nowva listens and speaks: the microphone array and speakers are built into the shell itself, so coaching arrives in the room around you with nothing to wear and nothing to hold.",
    "specs": [
      [
        "Audio in",
        "Integrated microphone array"
      ],
      [
        "Audio out",
        "Integrated speakers"
      ],
      [
        "Height",
        "2.10 m"
      ],
      [
        "Footprint",
        "1.72 × 1.28 m"
      ],
      [
        "Material",
        "High-grade polymer, soft-touch"
      ],
      [
        "Finish",
        "Seamless — no visible fixings"
      ]
    ]
  },
  LEFT_DOOR: {
    "displayName": "Sliding door — left",
    "category": "enclosure",
    "role": "One of a matched pair of full-height doors in the same polymer as the shell. They glide back to open the platform and close it away when the session ends, so the rack sits in the room as a quiet sculptural object rather than as a gym in the corner.",
    "specs": [
      [
        "Height",
        "2.03 m"
      ],
      [
        "Width",
        "0.94 m"
      ],
      [
        "Material",
        "High-grade polymer, soft-touch"
      ],
      [
        "Action",
        "Full-height slide"
      ]
    ]
  },
  RIGHT_DOOR: {
    "displayName": "Sliding door — right",
    "category": "enclosure",
    "role": "The mirrored half of the pair. Closed, the two doors meet flush against the shell with no visible seam hardware; open, they clear the full width of the platform.",
    "specs": [
      [
        "Height",
        "2.03 m"
      ],
      [
        "Width",
        "0.94 m"
      ],
      [
        "Material",
        "High-grade polymer, soft-touch"
      ],
      [
        "Action",
        "Full-height slide"
      ]
    ]
  },
  BARBELL_PUT_UP: {
    "displayName": "Barbell",
    "category": "training",
    "role": "The bar, racked at working height and ready. Sleeves are sized for standard loading, so your own plates fit.",
    "specs": [
      [
        "Length",
        "1.79 m"
      ],
      [
        "Sleeve",
        "80 mm across collars"
      ]
    ]
  },
  BARBELL_STAND: {
    "displayName": "Bar catch",
    "category": "training",
    "role": "The cradle the bar rests in between sets. It moves up and down the upright's adjustment column, so the rack meets your setup rather than the other way round.",
    "specs": [
      [
        "Adjustment",
        "Along the upright column"
      ],
      [
        "Size",
        "197 × 147 mm"
      ]
    ]
  },
  "45_PLATE_3": {
    "displayName": "45 plate — loaded",
    "category": "training",
    "role": "Loaded on the bar and ready to lift.",
    "specs": [
      [
        "Diameter",
        "450 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "45_PLATE_4": {
    "displayName": "45 plate — loaded",
    "category": "training",
    "role": "Loaded on the bar and ready to lift.",
    "specs": [
      [
        "Diameter",
        "450 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "45_PLATE": {
    "displayName": "45 plate — stored",
    "category": "training",
    "role": "Parked on the rack's integrated storage peg. Weight lives on the frame, never on the floor, so the platform stays clear.",
    "specs": [
      [
        "Diameter",
        "450 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "45_PLATE_1": {
    "displayName": "45 plate — stored",
    "category": "training",
    "role": "Parked on the rack's integrated storage peg. Weight lives on the frame, never on the floor, so the platform stays clear.",
    "specs": [
      [
        "Diameter",
        "450 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "45_PLATE_2": {
    "displayName": "45 plate — stored",
    "category": "training",
    "role": "Parked on the rack's integrated storage peg. Weight lives on the frame, never on the floor, so the platform stays clear.",
    "specs": [
      [
        "Diameter",
        "450 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "45_PLATE_5": {
    "displayName": "45 plate — stored",
    "category": "training",
    "role": "Parked on the rack's integrated storage peg. Weight lives on the frame, never on the floor, so the platform stays clear.",
    "specs": [
      [
        "Diameter",
        "450 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "25_PLATE": {
    "displayName": "25 plate — stored",
    "category": "training",
    "role": "The smaller increment, stored on its own peg within reach of the platform.",
    "specs": [
      [
        "Diameter",
        "290 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "25_PLATE_1": {
    "displayName": "25 plate — stored",
    "category": "training",
    "role": "The smaller increment, stored on its own peg within reach of the platform.",
    "specs": [
      [
        "Diameter",
        "290 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "25_PLATE_2": {
    "displayName": "25 plate — stored",
    "category": "training",
    "role": "The smaller increment, stored on its own peg within reach of the platform.",
    "specs": [
      [
        "Diameter",
        "290 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  "25_PLATE_3": {
    "displayName": "25 plate — stored",
    "category": "training",
    "role": "The smaller increment, stored on its own peg within reach of the platform.",
    "specs": [
      [
        "Diameter",
        "290 mm"
      ],
      [
        "Thickness",
        "36 mm"
      ]
    ]
  },
  MAINFRAME_1: {
    "displayName": "Bench frame",
    "category": "bench",
    "role": "The bench's structural spine. It folds flat and stows inside the shell, so closing the doors leaves nothing behind in the room.",
    "specs": [
      [
        "Length",
        "1.22 m"
      ],
      [
        "Stowage",
        "Folds flat inside the shell"
      ]
    ]
  },
  BACKSEAT: {
    "displayName": "Backrest pad",
    "category": "bench",
    "role": "Full-length upholstered backrest, matched in material and firmness to the seat.",
    "specs": [
      [
        "Length",
        "748 mm"
      ],
      [
        "Width",
        "250 mm"
      ]
    ]
  },
  FRONT_SEAT: {
    "displayName": "Seat pad",
    "category": "bench",
    "role": "Firm enough to press from, forgiving enough to sit on between sets.",
    "specs": [
      [
        "Length",
        "325 mm"
      ],
      [
        "Width",
        "250 mm"
      ]
    ]
  },
  FRONT_SEAT_INCLINER: {
    "displayName": "Incline mechanism",
    "category": "bench",
    "role": "Sets the backrest angle from flat to upright, detented so it holds position under load.",
    "specs": [
      [
        "Range",
        "Flat to upright"
      ]
    ]
  },
  SLIDER_SUPPORTER: {
    "displayName": "Slider rail",
    "category": "bench",
    "role": "The rail the seat carriage travels along when the bench reconfigures.",
    "specs": [
      [
        "Travel",
        "404 mm"
      ]
    ]
  },
  SLIDER_1: {
    "displayName": "Slider carriage",
    "category": "bench",
    "role": "Locks the seat at each position along the rail.",
    "specs": []
  },
  UNDERSUPPORT: {
    "displayName": "Base foot",
    "category": "bench",
    "role": "Cross-foot that spreads the bench's load into the platform.",
    "specs": [
      [
        "Width",
        "400 mm"
      ]
    ]
  },
  BACKSEATSUPPORT: {
    "displayName": "Backrest arm",
    "category": "bench",
    "role": "One of a pair of arms carrying the backrest through its incline range.",
    "specs": []
  },
  BACKSEATSUPPORT_1: {
    "displayName": "Backrest arm",
    "category": "bench",
    "role": "One of a pair of arms carrying the backrest through its incline range.",
    "specs": []
  },
  FRONTSEATSUPPORT: {
    "displayName": "Seat bracket",
    "category": "bench",
    "role": "One of a pair tying the seat pad to the carriage.",
    "specs": []
  },
  FRONTSEATSUPPORT_1: {
    "displayName": "Seat bracket",
    "category": "bench",
    "role": "One of a pair tying the seat pad to the carriage.",
    "specs": []
  },
  MAINFRAME: {
    "displayName": "Pivot pin",
    "category": "hardware",
    "role": "Pin in the bench's folding linkage.",
    "specs": []
  },
  SOCKET_HEAD_CAP_SCREW_AI_HX_SHCS_019_32X4X1125_N: {
    "displayName": "Pivot bolt — long",
    "category": "hardware",
    "role": "Socket-head cap screw at the bench's main pivot.",
    "specs": [
      [
        "Length",
        "106 mm"
      ]
    ]
  },
  SOCKET_HEAD_CAP_SCREW_AI_HX_SHCS_019_32X2X1125_N: {
    "displayName": "Pivot bolt — short",
    "category": "hardware",
    "role": "Socket-head cap screw in the lower linkage.",
    "specs": [
      [
        "Length",
        "56 mm"
      ]
    ]
  },
  WASHER: {
    "displayName": "Washer",
    "category": "hardware",
    "role": "Spreads load at a pivot joint.",
    "specs": []
  },
  WASHER_1: {
    "displayName": "Washer",
    "category": "hardware",
    "role": "Spreads load at a pivot joint.",
    "specs": []
  }
};

export function contentFor(id: string): PartContent {
  return partContent[id] ?? {};
}

export function displayNameFor(id: string, nodeName: string): string {
  return partContent[id]?.displayName || nodeName;
}
