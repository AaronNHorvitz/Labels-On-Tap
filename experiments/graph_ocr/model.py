"""Small PyTorch graph model for OCR evidence scoring.

The model is deliberately compact. It is meant to test whether OCR box geometry
and local graph context improve field matching. It is not a replacement OCR
recognizer and does not need PyTorch Geometric for the first proof of concept.
"""

from __future__ import annotations

import torch
from torch import nn


class GraphEvidenceScorer(nn.Module):
    """Message-passing scorer for one OCR-box graph.

    Parameters
    ----------
    input_dim:
        Number of node features.
    hidden_dim:
        Hidden channel width for node embeddings.
    layers:
        Number of lightweight message-passing layers.
    dropout:
        Dropout probability used after each graph update.
    """

    def __init__(
        self,
        *,
        input_dim: int,
        summary_dim: int,
        hidden_dim: int = 64,
        layers: int = 2,
        dropout: float = 0.10,
    ) -> None:
        super().__init__()
        self.input = nn.Linear(input_dim, hidden_dim)
        self.self_layers = nn.ModuleList(nn.Linear(hidden_dim, hidden_dim) for _ in range(layers))
        self.neighbor_layers = nn.ModuleList(nn.Linear(hidden_dim, hidden_dim) for _ in range(layers))
        self.attention = nn.Linear(hidden_dim, 1)
        self.summary = nn.Sequential(
            nn.Linear(summary_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.output = nn.Sequential(
            nn.Linear(hidden_dim * 3, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, 1),
        )
        self.activation = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x: torch.Tensor, adj: torch.Tensor, summary_x: torch.Tensor) -> torch.Tensor:
        """Return one logit for one variable-size OCR graph."""

        h = self.activation(self.input(x))
        for self_layer, neighbor_layer in zip(self.self_layers, self.neighbor_layers):
            neighbor_h = adj @ h
            h = self.activation(self_layer(h) + neighbor_layer(neighbor_h))
            h = self.dropout(h)

        attention_weights = torch.softmax(self.attention(h).squeeze(-1), dim=0).unsqueeze(-1)
        pooled = (attention_weights * h).sum(dim=0)
        max_pooled = h.max(dim=0).values
        summary = self.summary(summary_x)
        return self.output(torch.cat([pooled, max_pooled, summary], dim=0)).squeeze(-1)
