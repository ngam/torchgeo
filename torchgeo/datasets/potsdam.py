# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Potsdam dataset."""

import os
from typing import Any, Callable, Dict, Optional

import matplotlib.pyplot as plt
import numpy as np
import pytorch_lightning as pl
import rasterio
import torch
from matplotlib.figure import Figure
from PIL import Image
from torch import Tensor
from torch.utils.data import DataLoader
from torchvision.transforms import Compose

from ..datasets.utils import dataset_split, draw_semantic_segmentation_masks
from .geo import VisionDataset
from .utils import check_integrity, extract_archive, rgb_to_mask


class Potsdam2D(VisionDataset):
    """Potsdam 2D Semantic Segmentation dataset.

    The `Potsdam <https://www2.isprs.org/commissions/comm2/wg4/benchmark/2d-sem-label-potsdam/>`_
    dataset is a dataset for urban semantic segmentation used in the 2D Semantic Labeling
    Contest - Potsdam. This dataset uses the "4_Ortho_RGBIR.zip" and "5_Labels_all.zip"
    files to create the train/test sets used in the challenge. The dataset can be
    requested at the challenge homepage. Note, the server contains additional data
    for 3D Semantic Labeling which are currently not supported.

    Dataset format:

    * images are 4-channel geotiffs
    * masks are 3-channel geotiffs with unique RGB values representing the class

    Dataset classes:

    0. Clutter/background
    1. Impervious surfaces
    2. Building
    3. Low Vegetation
    4. Tree
    5. Car

    If you use this dataset in your research, please cite the following paper:

    * https://doi.org/10.5194/isprsannals-I-3-293-2012

    .. versionadded:: 0.2
    """  # noqa: E501

    filenames = ["4_Ortho_RGBIR.zip", "5_Labels_all.zip"]
    md5s = ["c4a8f7d8c7196dd4eba4addd0aae10c1", "cf7403c1a97c0d279414db"]
    image_root = "4_Ortho_RGBIR"
    splits = {
        "train": [
            "top_potsdam_2_10",
            "top_potsdam_2_11",
            "top_potsdam_2_12",
            "top_potsdam_3_10",
            "top_potsdam_3_11",
            "top_potsdam_3_12",
            "top_potsdam_4_10",
            "top_potsdam_4_11",
            "top_potsdam_4_12",
            "top_potsdam_5_10",
            "top_potsdam_5_11",
            "top_potsdam_5_12",
            "top_potsdam_6_10",
            "top_potsdam_6_11",
            "top_potsdam_6_12",
            "top_potsdam_6_7",
            "top_potsdam_6_8",
            "top_potsdam_6_9",
            "top_potsdam_7_10",
            "top_potsdam_7_11",
            "top_potsdam_7_12",
            "top_potsdam_7_7",
            "top_potsdam_7_8",
            "top_potsdam_7_9",
        ],
        "test": [
            "top_potsdam_5_15",
            "top_potsdam_6_15",
            "top_potsdam_6_13",
            "top_potsdam_3_13",
            "top_potsdam_4_14",
            "top_potsdam_6_14",
            "top_potsdam_5_14",
            "top_potsdam_2_13",
            "top_potsdam_4_15",
            "top_potsdam_2_14",
            "top_potsdam_5_13",
            "top_potsdam_4_13",
            "top_potsdam_3_14",
            "top_potsdam_7_13",
        ],
    }
    classes = [
        "Clutter/background",
        "Impervious surfaces",
        "Building",
        "Low Vegetation",
        "Tree",
        "Car",
    ]
    colormap = [
        (255, 0, 0),
        (255, 255, 255),
        (0, 0, 255),
        (0, 255, 255),
        (0, 255, 0),
        (255, 255, 0),
    ]

    def __init__(
        self,
        root: str = "data",
        split: str = "train",
        transforms: Optional[Callable[[Dict[str, Tensor]], Dict[str, Tensor]]] = None,
        checksum: bool = False,
    ) -> None:
        """Initialize a new Potsdam dataset instance.

        Args:
            root: root directory where dataset can be found
            split: one of "train" or "test"
            transforms: a function/transform that takes input sample and its target as
                entry and returns a transformed version
            checksum: if True, check the MD5 of the downloaded files (may be slow)
        """
        assert split in self.splits
        self.root = root
        self.split = split
        self.transforms = transforms
        self.checksum = checksum

        self._verify()

        self.files = []
        for name in self.splits[split]:
            image = os.path.join(root, self.image_root, name) + "_RGBIR.tif"
            mask = os.path.join(root, name) + "_label.tif"
            if os.path.exists(image) and os.path.exists(mask):
                self.files.append(dict(image=image, mask=mask))

    def __getitem__(self, index: int) -> Dict[str, Tensor]:
        """Return an index within the dataset.

        Args:
            index: index to return

        Returns:
            data and label at that index
        """
        image = self._load_image(index)
        mask = self._load_target(index)
        sample = {"image": image, "mask": mask}

        if self.transforms is not None:
            sample = self.transforms(sample)

        return sample

    def __len__(self) -> int:
        """Return the number of data points in the dataset.

        Returns:
            length of the dataset
        """
        return len(self.files)

    def _load_image(self, index: int) -> Tensor:
        """Load a single image.

        Args:
            index: index to return

        Returns:
            the image
        """
        path = self.files[index]["image"]
        with rasterio.open(path) as f:
            array = f.read()
            tensor: Tensor = torch.from_numpy(array)  # type: ignore[attr-defined]
            return tensor

    def _load_target(self, index: int) -> Tensor:
        """Load the target mask for a single image.

        Args:
            index: index to return

        Returns:
            the target mask
        """
        path = self.files[index]["mask"]
        with Image.open(path) as img:
            array = np.array(img.convert("RGB"))
            array = rgb_to_mask(array, self.colormap)
            tensor: Tensor = torch.from_numpy(array)  # type: ignore[attr-defined]
            # Convert from HxWxC to CxHxW
            tensor = tensor.to(torch.long)  # type: ignore[attr-defined]
        return tensor

    def _verify(self) -> None:
        """Verify the integrity of the dataset.

        Raises:
            RuntimeError: if checksum fails or the dataset is not downloaded
        """
        # Check if the files already exist
        if os.path.exists(os.path.join(self.root, self.image_root)):
            return

        # Check if .zip files already exists (if so extract)
        exists = []
        for filename, md5 in zip(self.filenames, self.md5s):
            filepath = os.path.join(self.root, filename)
            if os.path.isfile(filepath):
                if self.checksum and not check_integrity(filepath, md5):
                    raise RuntimeError("Dataset found, but corrupted.")
                exists.append(True)
                extract_archive(filepath)
            else:
                exists.append(False)

        if all(exists):
            return

        # Check if the user requested to download the dataset
        raise RuntimeError(
            "Dataset not found in `root` directory, either specify a different"
            + " `root` directory or manually download the dataset to this directory."
        )

    def plot(
        self,
        sample: Dict[str, Tensor],
        show_titles: bool = True,
        suptitle: Optional[str] = None,
        alpha: float = 0.5,
    ) -> Figure:
        """Plot a sample from the dataset.

        Args:
            sample: a sample returned by :meth:`__getitem__`
            show_titles: flag indicating whether to show titles above each panel
            suptitle: optional string to use as a suptitle
            alpha: opacity with which to render predictions on top of the imagery

        Returns:
            a matplotlib Figure with the rendered sample
        """
        ncols = 1
        image1 = draw_semantic_segmentation_masks(
            sample["image"][:3],
            sample["mask"],
            alpha=alpha,
            colors=self.colormap,  # type: ignore[arg-type]
        )
        if "prediction" in sample:
            ncols += 1
            image2 = draw_semantic_segmentation_masks(
                sample["image"][:3],
                sample["prediction"],
                alpha=alpha,
                colors=self.colormap,  # type: ignore[arg-type]
            )

        fig, axs = plt.subplots(ncols=ncols, figsize=(ncols * 10, 10))
        if ncols > 1:
            (ax0, ax1) = axs
        else:
            ax0 = axs

        ax0.imshow(image1)
        ax0.axis("off")
        if ncols > 1:
            ax1.imshow(image2)
            ax1.axis("off")

        if show_titles:
            ax0.set_title("Ground Truth")
            if ncols > 1:
                ax1.set_title("Predictions")

        if suptitle is not None:
            plt.suptitle(suptitle)

        return fig


class Potsdam2DDataModule(pl.LightningDataModule):
    """LightningDataModule implementation for the Potsdam2D dataset.

    Uses the train/test splits from the dataset.

    .. versionadded: 0.2
    """

    def __init__(
        self,
        root_dir: str,
        batch_size: int = 64,
        num_workers: int = 0,
        val_split_pct: float = 0.2,
        **kwargs: Any,
    ) -> None:
        """Initialize a LightningDataModule for Potsdam2D based DataLoaders.

        Args:
            root_dir: The ``root`` argument to pass to the Potsdam2D Dataset classes
            batch_size: The batch size to use in all created DataLoaders
            num_workers: The number of workers to use in all created DataLoaders
            val_split_pct: What percentage of the dataset to use as a validation set
        """
        super().__init__()  # type: ignore[no-untyped-call]
        self.root_dir = root_dir
        self.batch_size = batch_size
        self.num_workers = num_workers
        self.val_split_pct = val_split_pct

    def preprocess(self, sample: Dict[str, Any]) -> Dict[str, Any]:
        """Transform a single sample from the Dataset.

        Args:
            sample: input image dictionary

        Returns:
            preprocessed sample
        """
        sample["image"] = sample["image"].float()
        sample["image"] /= 255.0
        return sample

    def setup(self, stage: Optional[str] = None) -> None:
        """Initialize the main ``Dataset`` objects.

        This method is called once per GPU per run.

        Args:
            stage: stage to set up
        """
        transforms = Compose([self.preprocess])

        dataset = Potsdam2D(self.root_dir, "train", transforms=transforms)

        if self.val_split_pct > 0.0:
            self.train_dataset, self.val_dataset, _ = dataset_split(
                dataset, val_pct=self.val_split_pct, test_pct=0.0
            )
        else:
            self.train_dataset = dataset  # type: ignore[assignment]
            self.val_dataset = None  # type: ignore[assignment]

        self.test_dataset = Potsdam2D(self.root_dir, "test", transforms=transforms)

    def train_dataloader(self) -> DataLoader[Any]:
        """Return a DataLoader for training.

        Returns:
            training data loader
        """
        return DataLoader(
            self.train_dataset,
            batch_size=self.batch_size,
            num_workers=self.num_workers,
            shuffle=True,
        )

    def val_dataloader(self) -> DataLoader[Any]:
        """Return a DataLoader for validation.

        Returns:
            validation data loader
        """
        if self.val_split_pct == 0.0:
            return self.train_dataloader()
        else:
            return DataLoader(
                self.val_dataset,
                batch_size=self.batch_size,
                num_workers=self.num_workers,
                shuffle=False,
            )

    def test_dataloader(self) -> DataLoader[Any]:
        """Return a DataLoader for testing.

        Returns:
            testing data loader
        """
        return DataLoader(
            self.test_dataset,
            batch_size=self.batch_size,
            num_workers=self.num_workers,
            shuffle=False,
        )
