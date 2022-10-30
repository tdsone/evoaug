import torch
from pytorch_lightning.core.lightning import LightningModule
import numpy as np


class RobustModel(LightningModule):
    """supervised learning model or supervised transfer learning model with data augmentation
        
        Parameters:
            model_untrained: untrained supervised model *OR* untrained supervised 
                transfer learning model into which trained first-layer convolutional filters 
                from GRIM have been inserted (see supervised.py); should be an instance 
                of a class inheriting from torch.nn.Module
            loss_criterion: loss criterion to use--should be a function, e.g. nn.BCELoss()
            
    """
    def __init__(self, model, criterion, optimizer, augment_list=[], max_augs_per_seq=2, hard_aug=True, finetune=False, inference_aug=False):
        super().__init__()
        self.model = model
        self.criterion = criterion 
        self.optimizer = optimizer
        self.augment_list = augment_list
        self.max_augs_per_seq = np.minimum(max_augs_per_seq, len(augment_list))
        self.hard_aug = hard_aug
        self.inference_aug = inference_aug
        self.optimizer = optimizer
        self.max_num_aug = len(augment_list)
        self.insert_max = augment_max_len(augment_list)
        self.finetune = finetune


    def forward(self, x):
        y_hat = self.model(x)
        return y_hat
    

    def configure_optimizers(self):
        return self.optimizer


    def training_step(self, batch, batch_idx):
        x, y = batch
        if self.finetune:
            if self.insert_max: 
                x = self._pad_end(x)
        else:
            x = self._apply_augment(x)
        y_hat = self(x)
        loss = self.criterion(y_hat, y)
        self.log('train_loss', loss, on_step=False, on_epoch=True, prog_bar=True, logger=True)        
        return loss
    

    def validation_step(self, batch, batch_idx):
        x, y = batch 
        if self.inference_aug:
            x = self._apply_augment(x)
        else:
            if self.insert_max:
                x = self._pad_end(x)
        y_hat = self(x)
        loss = self.criterion(y_hat, y)
        self.log('val_loss', loss, on_step=False, on_epoch=True, prog_bar=True)
    

    def test_step(self, batch, batch_idx):
        x, y = batch
        if self.inference_aug:
            x = self._apply_augment(x)
        else:
            if self.insert_max:
                x = self._pad_end(x)
        y_hat = self(x)
        loss = self.criterion(y_hat, y)
        self.log('test_loss', loss, on_step=False, on_epoch=True, prog_bar=True)
        

    def predict_step(self, batch, batch_idx):
        x = batch 
        if self.inference_aug:
            x = self._apply_augment(x)
        else:
            if self.insert_max:
                x = self._pad_end(x)
        return self(x)


    def _sample_aug_combos(self, batch_size):
        # number of augmentations per sequence
        if self.hard_aug:
            batch_num_aug = self.max_augs_per_seq * np.ones((batch_size,), dtype=int)
        else:
            batch_num_aug = np.random.randint(1, self.max_augs_per_seq + 1, (batch_size,))
        aug_combos = [ list(sorted(np.random.choice(self.max_num_aug, sample, replace=False))) for sample in batch_num_aug ]
        return aug_combos


    def _apply_augment(self, x):
        # number of augmentations per sequence
        batch_size = x.shape[0]
        aug_combos = self._sample_aug_combos(batch_size)

        # apply augmentation combination to sequences
        x_new = []
        for aug_indices, seq in zip(aug_combos, x):
            seq = torch.unsqueeze(seq, dim=0)
            insert_status = True
            for aug_index in aug_indices:
                seq = self.augment_list[aug_index](seq)
                if hasattr(self.augment_list[aug_index], 'insert_max'):
                    insert_status = False
            if insert_status:
                if self.insert_max:
                    seq = self._pad_end(seq)
            x_new.append(seq)
        return torch.cat(x_new)


    def _pad_end(self, x):
        N_batch, A, L = x.shape
        a = torch.eye(A)
        p = torch.tensor([1/A for _ in range(A)])
        padding = torch.stack([a[p.multinomial(self.insert_max, replacement=True)].transpose(0,1) for _ in range(N_batch)]).to(x.device)
        x_padded = torch.cat( [x, padding.to(x.device)], dim=2 )
        return x_padded





def load_model_from_checkpoint(model, checkpoint_path):
    return model.load_from_checkpoint(checkpoint_path, 
                                     model=model.model, 
                                     criterion=model.criterion, 
                                     optimizer=model.optimizer,
                                     augment_list=model.augment_list, 
                                     max_augs_per_seq=model.max_augs_per_seq, 
                                     hard_aug=model.hard_aug, 
                                     finetune=model.finetune,
                                     inference_aug=model.inference_aug
                                     )


#------------------------------------------------------------------------
# Helper function
#------------------------------------------------------------------------


def augment_max_len(augment_list):
    insert_max = 0
    for augment in augment_list:
        if hasattr(augment, 'insert_max'):
            insert_max = augment.insert_max
    return insert_max
