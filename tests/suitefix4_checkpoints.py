"""Load hashed, explicitly independent baseline substrates into test files."""
import base64
import io
import pathlib
import pickle


class _Unpickler(pickle.Unpickler):
    def __init__(self, data, monrace, directory, old_directory=None):
        super().__init__(io.BytesIO(data))
        self.monrace = monrace
        self.directory = directory
        self.old_directory = old_directory

    def persistent_load(self, pid):
        assert pid == "monrace"
        return self.monrace

    def find_class(self, module, name):
        if module in {"pathlib", "pathlib._local"} and name in {
            "Path", "WindowsPath", "PosixPath", "PurePath", "PureWindowsPath", "PurePosixPath",
        }:
            constructor = getattr(pathlib, name)
            def path(*parts):
                value = constructor(*parts)
                if self.old_directory is not None and value.is_relative_to(self.old_directory):
                    return self.directory / value.relative_to(self.old_directory)
                return value
            return path
        return super().find_class(module, name)


def restore(record, monrace, directory):
    """Rebase every nested Path as well as the policy's top-level paths."""
    data = base64.b64decode(record["policy"])
    probe = _Unpickler(data, monrace, directory).load()
    old_directory = probe._character_calibration_path.parent
    policy = _Unpickler(data, monrace, directory, old_directory).load()
    for name, encoded in record["files"].items():
        target = directory / name
        assert target.resolve().is_relative_to(directory.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(encoded))
    return policy
