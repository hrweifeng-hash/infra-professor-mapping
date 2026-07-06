import html
import gzip
import shutil
from pathlib import Path
import html.entities


def normalize_dataset(input_path: str | Path, output_path: str | Path, *, chunk_size: int = 1_048_576, tail_size: int = 4096) -> Path:
    """Normalize `input_path` and write normalized output to `output_path`.

    - Decodes known named entities into their Unicode characters.
    - Escapes unknown entities and stray XML-critical characters so the
      resulting file is safe for XML parsing.
    - Operates in a streaming manner and writes a gzipped output with
      deterministic `mtime=0` for repeatability.
    """
    inp = Path(input_path)
    outp = Path(output_path)
    if not inp.exists():
        raise FileNotFoundError(inp)

    def flush_entity(buf: str) -> str:
        # buf starts with '&' and may or may not include trailing ';'
        token = buf[1:]
        if not token:
            return '&amp;'
        if token.startswith('#'):
            return '&' + token
        name = token.rstrip(';')
        # Preserve predefined XML entities (do not decode them)
        if name in ("amp", "lt", "gt", "quot", "apos"):
            # return the original entity sequence (with semicolon if present)
            return '&' + name + (';' if token.endswith(';') else '')

        cp = html.entities.name2codepoint.get(name)
        if cp is not None:
            return chr(cp)

        # unknown: escape the ampersand so the parser treats it as literal
        return '&amp;' + name + (';' if token.endswith(';') else '')

    with gzip.open(inp, 'rt', encoding='utf-8', errors='replace') as rf:
        with open(outp, 'wb') as wf_raw:
            with gzip.GzipFile(fileobj=wf_raw, mode='wb', mtime=0) as wf:
                in_tag = False
                entity_buf = ''
                tail = ''

                while True:
                    chunk = rf.read(chunk_size)
                    if not chunk:
                        break

                    s = tail + chunk
                    if len(s) > tail_size:
                        proc, tail = s[:-tail_size], s[-tail_size:]
                    else:
                        proc, tail = '', s

                    out_chars = []
                    i = 0
                    L = len(proc)
                    while i < L:
                        ch = proc[i]
                        if entity_buf:
                            entity_buf += ch
                            # flush entity on semicolon or if it grows too long
                            if ch == ';' or len(entity_buf) > 128:
                                out_chars.append(flush_entity(entity_buf))
                                entity_buf = ''
                            i += 1
                            continue

                        if ch == '&':
                            entity_buf = '&'
                            i += 1
                            continue

                        if in_tag:
                            out_chars.append(ch)
                            if ch == '>':
                                in_tag = False
                            i += 1
                            continue

                        # not in tag and not in entity
                        if ch == '<':
                            in_tag = True
                            out_chars.append('<')
                            i += 1
                            continue

                        if ch == '>':
                            out_chars.append('&gt;')
                            i += 1
                            continue

                        out_chars.append(ch)
                        i += 1

                    wf.write(''.join(out_chars).encode('utf-8'))

                # process tail
                s = tail
                out_chars = []
                i = 0
                L = len(s)
                while i < L:
                    ch = s[i]
                    if entity_buf:
                        entity_buf += ch
                        if ch == ';' or len(entity_buf) > 128:
                            out_chars.append(flush_entity(entity_buf))
                            entity_buf = ''
                        i += 1
                        continue

                    if ch == '&':
                        entity_buf = '&'
                        i += 1
                        continue

                    if in_tag:
                        out_chars.append(ch)
                        if ch == '>':
                            in_tag = False
                        i += 1
                        continue

                    if ch == '<':
                        in_tag = True
                        out_chars.append('<')
                        i += 1
                        continue

                    if ch == '>':
                        out_chars.append('&gt;')
                        i += 1
                        continue

                    out_chars.append(ch)
                    i += 1

                if entity_buf:
                    out_chars.append(flush_entity(entity_buf))
                    entity_buf = ''

                wf.write(''.join(out_chars).encode('utf-8'))

    return outp


def normalize_dataset_inplace(input_path: str | Path, *, chunk_size: int = 1_048_576, tail_size: int = 4096) -> Path:
    inp = Path(input_path)
    out_tmp = inp.with_suffix('.normalized.tmp.gz')
    normalize_dataset(inp, out_tmp, chunk_size=chunk_size, tail_size=tail_size)
    shutil.move(str(out_tmp), str(inp))
    return inp


__all__ = ["normalize_dataset", "normalize_dataset_inplace"]
