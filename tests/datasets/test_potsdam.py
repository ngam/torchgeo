# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

import os
import shutil
from pathlib import Path
from typing import Generator

import matplotlib.pyplot as plt
import pytest
import torch
import torch.nn as nn
from _pytest.fixtures import SubRequest
from _pytest.monkeypatch import MonkeyPatch

from torchgeo.datasets import Potsdam2D, Potsdam2DDataModule


class TestPotsdam2D:
    @pytest.fixture(params=["train", "test"])
    def dataset(
        self, monkeypatch: Generator[MonkeyPatch, None, None], request: SubRequest
    ) -> Potsdam2D:
        md5s = ["e47175da529c5844052c7d483b483a30", "0cb795003a01154a72db7efaabbc76ae"]
        splits = {
            "train": ["top_potsdam_2_10", "top_potsdam_2_11"],
            "test": ["top_potsdam_5_15", "top_potsdam_6_15"],
        }
        monkeypatch.setattr(Potsdam2D, "md5s", md5s)  # type: ignore[attr-defined]
        monkeypatch.setattr(Potsdam2D, "splits", splits)  # type: ignore[attr-defined]
        root = os.path.join("tests", "data", "potsdam")
        split = request.param
        transforms = nn.Identity()  # type: ignore[attr-defined]
        return Potsdam2D(root, split, transforms, checksum=True)

    def test_getitem(self, dataset: Potsdam2D) -> None:
        x = dataset[0]
        assert isinstance(x, dict)
        assert isinstance(x["image"], torch.Tensor)
        assert isinstance(x["mask"], torch.Tensor)

    def test_len(self, dataset: Potsdam2D) -> None:
        assert len(dataset) == 2

    def test_extract(self, tmp_path: Path) -> None:
        root = os.path.join("tests", "data", "potsdam")
        for filename in ["4_Ortho_RGBIR.zip", "5_Labels_all.zip"]:
            shutil.copyfile(
                os.path.join(root, filename), os.path.join(str(tmp_path), filename)
            )
        Potsdam2D(root=str(tmp_path))

    def test_corrupted(self, tmp_path: Path) -> None:
        with open(os.path.join(tmp_path, "4_Ortho_RGBIR.zip"), "w") as f:
            f.write("bad")
        with open(os.path.join(tmp_path, "5_Labels_all.zip"), "w") as f:
            f.write("bad")
        with pytest.raises(RuntimeError, match="Dataset found, but corrupted."):
            Potsdam2D(root=str(tmp_path), checksum=True)

    def test_invalid_split(self) -> None:
        with pytest.raises(AssertionError):
            Potsdam2D(split="foo")

    def test_not_downloaded(self, tmp_path: Path) -> None:
        with pytest.raises(RuntimeError, match="Dataset not found in `root` directory"):
            Potsdam2D(str(tmp_path))

    def test_plot(self, dataset: Potsdam2D) -> None:
        x = dataset[0].copy()
        dataset.plot(x, suptitle="Test")
        plt.close()
        dataset.plot(x, show_titles=False)
        plt.close()
        x["prediction"] = x["mask"].clone()
        dataset.plot(x)
        plt.close()


class TestPotsdam2DDataModule:
    @pytest.fixture(scope="class", params=[0.0, 0.5])
    def datamodule(self, request: SubRequest) -> Potsdam2DDataModule:
        root = os.path.join("tests", "data", "potsdam")
        batch_size = 1
        num_workers = 0
        val_split_size = request.param
        dm = Potsdam2DDataModule(
            root, batch_size, num_workers, val_split_pct=val_split_size
        )
        dm.prepare_data()
        dm.setup()
        return dm

    def test_train_dataloader(self, datamodule: Potsdam2DDataModule) -> None:
        next(iter(datamodule.train_dataloader()))

    def test_val_dataloader(self, datamodule: Potsdam2DDataModule) -> None:
        next(iter(datamodule.val_dataloader()))

    def test_test_dataloader(self, datamodule: Potsdam2DDataModule) -> None:
        next(iter(datamodule.test_dataloader()))
