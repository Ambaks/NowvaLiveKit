"""
Document Processor for CAG files

Parses CAG periodization document into structured sections that can be
processed by the propositional chunker.
"""
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .utils import get_token_count


logger = logging.getLogger(__name__)


@dataclass
class DocumentSection:
    """Represents a section from the CAG document"""
    section_number: Optional[int]
    section_title: str
    subsection: Optional[str]
    content: str
    token_count: int
    metadata: Dict[str, Any]

    def __post_init__(self):
        if self.token_count == 0:
            self.token_count = get_token_count(self.content)


@dataclass
class ParsedDocument:
    """Represents the fully parsed CAG document"""
    filepath: str
    title: str
    sections: List[DocumentSection]
    full_text: str
    total_tokens: int

    @property
    def num_sections(self) -> int:
        return len(self.sections)


class DocumentProcessor:
    """Parse CAG documents into structured sections"""

    # Regex patterns for section detection
    SECTION_PATTERN = re.compile(r'^##\s+(\d+)\.\s+(.+)$', re.MULTILINE)
    SUBSECTION_PATTERN = re.compile(r'^###\s+(.+)$', re.MULTILINE)

    @classmethod
    def parse_cag_file(cls, filepath: str) -> ParsedDocument:
        """
        Parse CAG periodization file into structured sections

        Args:
            filepath: Path to CAG file

        Returns:
            ParsedDocument with structured sections
        """
        logger.info(f"Parsing CAG file: {filepath}")

        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"CAG file not found: {filepath}")

        # Read full document
        with open(filepath, 'r', encoding='utf-8') as f:
            full_text = f.read()

        # Extract document title
        title_match = re.search(r'^# (.+)$', full_text, re.MULTILINE)
        title = title_match.group(1) if title_match else path.stem

        # Find all main sections (## N. TITLE)
        section_matches = list(cls.SECTION_PATTERN.finditer(full_text))

        sections = []
        for i, match in enumerate(section_matches):
            section_num = int(match.group(1))
            section_title = match.group(2).strip()
            section_start = match.end()

            # Determine section end (start of next section or EOF)
            if i + 1 < len(section_matches):
                section_end = section_matches[i + 1].start()
            else:
                section_end = len(full_text)

            section_content = full_text[section_start:section_end].strip()

            # Extract subsections if any
            subsection_matches = list(cls.SUBSECTION_PATTERN.finditer(section_content))

            if subsection_matches:
                # Split by subsections
                for j, sub_match in enumerate(subsection_matches):
                    subsection_title = sub_match.group(1).strip()
                    sub_start = sub_match.end()

                    # Determine subsection end
                    if j + 1 < len(subsection_matches):
                        sub_end = subsection_matches[j + 1].start()
                    else:
                        sub_end = len(section_content)

                    sub_content = section_content[sub_start:sub_end].strip()

                    if sub_content:  # Only add non-empty subsections
                        metadata = cls._extract_metadata(
                            section_title,
                            subsection_title,
                            sub_content
                        )

                        sections.append(DocumentSection(
                            section_number=section_num,
                            section_title=section_title,
                            subsection=subsection_title,
                            content=sub_content,
                            token_count=0,  # Will be calculated in __post_init__
                            metadata=metadata
                        ))
            else:
                # No subsections, treat entire section as one
                if section_content:
                    metadata = cls._extract_metadata(section_title, None, section_content)

                    sections.append(DocumentSection(
                        section_number=section_num,
                        section_title=section_title,
                        subsection=None,
                        content=section_content,
                        token_count=0,
                        metadata=metadata
                    ))

        total_tokens = get_token_count(full_text)

        logger.info(f"Parsed {len(sections)} sections from {filepath}")
        logger.info(f"Total tokens in document: {total_tokens:,}")

        return ParsedDocument(
            filepath=filepath,
            title=title,
            sections=sections,
            full_text=full_text,
            total_tokens=total_tokens
        )

    @staticmethod
    def _extract_metadata(
        section_title: str,
        subsection: Optional[str],
        content: str
    ) -> Dict[str, Any]:
        """
        Extract metadata from section content

        Args:
            section_title: Main section title
            subsection: Subsection title if any
            content: Section content

        Returns:
            Metadata dictionary
        """
        metadata = {
            "section_title": section_title,
            "subsection": subsection,
        }

        content_lower = content.lower()

        # Detect training focus
        training_focus = []
        if any(kw in content_lower for kw in ['strength', 'powerlifting', '1-5 reps', 'max']):
            training_focus.append('strength')
        if any(kw in content_lower for kw in ['hypertrophy', 'muscle growth', '8-12 reps', 'volume']):
            training_focus.append('hypertrophy')
        if any(kw in content_lower for kw in ['power', 'explosive', 'olympic', 'clean', 'snatch']):
            training_focus.append('power')
        if any(kw in content_lower for kw in ['athletic', 'sport', 'performance']):
            training_focus.append('athletic')

        metadata['training_focus'] = training_focus

        # Detect experience level
        experience_level = []
        if any(kw in content_lower for kw in ['novice', 'beginner', 'new lifter']):
            experience_level.append('novice')
        if any(kw in content_lower for kw in ['intermediate', 'experienced']):
            experience_level.append('intermediate')
        if any(kw in content_lower for kw in ['advanced', 'elite', 'competitive']):
            experience_level.append('advanced')

        metadata['experience_level'] = experience_level

        # Detect program structure keywords
        program_structures = []
        if any(kw in content_lower for kw in ['full body', 'full-body']):
            program_structures.append('full_body')
        if any(kw in content_lower for kw in ['upper/lower', 'upper lower']):
            program_structures.append('upper_lower')
        if any(kw in content_lower for kw in ['push/pull/legs', 'ppl']):
            program_structures.append('ppl')
        if any(kw in content_lower for kw in ['body part split', 'bro split']):
            program_structures.append('body_part_split')

        metadata['program_structures'] = program_structures

        # Detect if contains program template
        has_template = bool(re.search(r'```', content)) or bool(re.search(r'workout [a-z]:', content_lower))
        metadata['has_template'] = has_template

        # Detect content type
        if has_template:
            metadata['content_type'] = 'program_template'
        elif any(kw in section_title.lower() for kw in ['principle', 'concept', 'theory']):
            metadata['content_type'] = 'principle'
        elif 'exercise' in content_lower and ('list' in content_lower or 'selection' in content_lower):
            metadata['content_type'] = 'exercise_list'
        else:
            metadata['content_type'] = 'general'

        return metadata

    @classmethod
    def split_large_sections(
        cls,
        sections: List[DocumentSection],
        max_tokens: int = 2000
    ) -> List[DocumentSection]:
        """
        Split sections that are too large for processing

        Args:
            sections: List of document sections
            max_tokens: Maximum tokens per section

        Returns:
            List of sections with large ones split
        """
        result = []

        for section in sections:
            if section.token_count <= max_tokens:
                result.append(section)
            else:
                # Split by paragraphs
                paragraphs = section.content.split('\n\n')
                current_chunk = []
                current_tokens = 0

                for para in paragraphs:
                    para_tokens = get_token_count(para)

                    if current_tokens + para_tokens > max_tokens and current_chunk:
                        # Save current chunk
                        chunk_content = '\n\n'.join(current_chunk)
                        result.append(DocumentSection(
                            section_number=section.section_number,
                            section_title=section.section_title,
                            subsection=section.subsection,
                            content=chunk_content,
                            token_count=current_tokens,
                            metadata=section.metadata.copy()
                        ))
                        current_chunk = [para]
                        current_tokens = para_tokens
                    else:
                        current_chunk.append(para)
                        current_tokens += para_tokens

                # Add remaining
                if current_chunk:
                    chunk_content = '\n\n'.join(current_chunk)
                    result.append(DocumentSection(
                        section_number=section.section_number,
                        section_title=section.section_title,
                        subsection=section.subsection,
                        content=chunk_content,
                        token_count=current_tokens,
                        metadata=section.metadata.copy()
                    ))

                logger.info(
                    f"Split large section '{section.section_title}' "
                    f"({section.token_count} tokens) into {len([s for s in result if s.section_title == section.section_title])} parts"
                )

        return result
