#!/usr/bin/env python3
"""
Learning Engine CLI

Command-line interface for managing the learning engine service.

Usage:
    python learning_engine_cli.py train [--days 7] [--ewc-lambda 500]
    python learning_engine_cli.py train-jsonl --dataset /path/data.jsonl [--learning-rate 2e-4] [--epochs 3] [--batch-size 4]
    python learning_engine_cli.py fisher [--num-samples 1000]
    python learning_engine_cli.py list-adapters
    python learning_engine_cli.py deploy <version>
    python learning_engine_cli.py status
    python learning_engine_cli.py metrics
"""

import argparse
import asyncio
import httpx
import json
import sys
from typing import Optional


BASE_URL = "http://localhost:8003"


async def train(days: int, ewc_lambda: float, force: bool, base_url: str):
    """Trigger a training job"""
    print(f"Triggering training job...")
    print(f"  Days: {days}")
    print(f"  EWC Lambda: {ewc_lambda}")
    print(f"  Force: {force}")
    
    payload = {
        "days": days,
        "ewc_lambda": ewc_lambda,
        "force": force
    }
    
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(f"{base_url}/train", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✓ Training job started")
            print(f"  Job ID: {data['job_id']}")
            print(f"  Status: {data['status']}")
        else:
            print(f"\n✗ Failed to start training: {response.text}")
            sys.exit(1)


async def train_jsonl(
    dataset_path: str,
    learning_rate: Optional[float],
    epochs: Optional[int],
    batch_size: Optional[int],
    base_url: str
):
    """Trigger training from JSONL dataset."""
    print("Triggering JSONL training job...")
    print(f"  Dataset: {dataset_path}")
    if learning_rate is not None:
        print(f"  Learning rate: {learning_rate}")
    if epochs is not None:
        print(f"  Epochs: {epochs}")
    if batch_size is not None:
        print(f"  Batch size: {batch_size}")

    payload = {
        "dataset_path": dataset_path,
        "learning_rate": learning_rate,
        "epochs": epochs,
        "batch_size": batch_size,
    }

    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(f"{base_url}/train/jsonl", json=payload)

        if response.status_code == 200:
            data = response.json()
            print("\n✓ JSONL training job started")
            print(f"  Job ID: {data['job_id']}")
            print(f"  Status: {data['status']}")
        else:
            print(f"\n✗ Failed to start JSONL training: {response.text}")
            sys.exit(1)


async def calculate_fisher(num_samples: int, adapter_version: Optional[str], base_url: str):
    """Calculate Fisher Information Matrix"""
    print(f"Calculating Fisher Information Matrix...")
    print(f"  Samples: {num_samples}")
    if adapter_version:
        print(f"  Adapter: {adapter_version}")
    
    payload = {
        "num_samples": num_samples
    }
    if adapter_version:
        payload["adapter_version"] = adapter_version
    
    async with httpx.AsyncClient(timeout=600.0) as client:
        response = await client.post(f"{base_url}/fisher/calculate", json=payload)
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✓ Fisher calculation started")
            print(f"  Version: {data['fisher_version']}")
        else:
            print(f"\n✗ Failed to start Fisher calculation: {response.text}")
            sys.exit(1)


async def list_adapters(base_url: str):
    """List all adapters"""
    print("Listing adapters...")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/adapters")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nFound {data['total']} adapter(s):\n")
            
            for adapter in data['adapters']:
                print(f"  Version: {adapter['version']}")
                if 'job_id' in adapter:
                    print(f"    Job ID: {adapter['job_id']}")
                if 'samples' in adapter:
                    print(f"    Samples: {adapter['samples']}")
                if 'train_loss' in adapter:
                    print(f"    Train Loss: {adapter['train_loss']:.4f}")
                if 'timestamp' in adapter:
                    print(f"    Timestamp: {adapter['timestamp']}")
                print()
        else:
            print(f"\n✗ Failed to list adapters: {response.text}")
            sys.exit(1)


async def get_adapter_info(version: str, base_url: str):
    """Get adapter information"""
    print(f"Getting adapter info for {version}...")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/adapters/{version}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\nAdapter {version}:")
            print(json.dumps(data, indent=2))
        else:
            print(f"\n✗ Failed to get adapter info: {response.text}")
            sys.exit(1)


async def deploy_adapter(version: str, base_url: str):
    """Deploy an adapter"""
    print(f"Deploying adapter {version}...")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{base_url}/adapters/{version}/deploy")
        
        if response.status_code == 200:
            data = response.json()
            print(f"\n✓ Adapter deployed")
            print(f"  Version: {data['version']}")
            print(f"  Status: {data['status']}")
            print(f"  Path: {data['path']}")
        else:
            print(f"\n✗ Failed to deploy adapter: {response.text}")
            sys.exit(1)


async def get_status(base_url: str):
    """Get training status"""
    print("Getting training status...")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/training/status")
        
        if response.status_code == 200:
            data = response.json()
            print("\nTraining Status:")
            print(json.dumps(data, indent=2))
        else:
            print(f"\n✗ Failed to get status: {response.text}")
            sys.exit(1)


async def get_metrics(base_url: str):
    """Get training metrics"""
    print("Getting training metrics...")
    
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/metrics")
        
        if response.status_code == 200:
            data = response.json()
            print("\nTraining Metrics:")
            print(json.dumps(data, indent=2))
        else:
            print(f"\n✗ Failed to get metrics: {response.text}")
            sys.exit(1)


async def health_check(base_url: str):
    """Check service health"""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/health")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Service Status: {data['status']}")
            print(f"Version: {data['version']}")
            print("\nComponents:")
            for component, status in data['components'].items():
                print(f"  {component}: {status}")
        else:
            print(f"✗ Service unhealthy: {response.text}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Learning Engine CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help="Base URL for learning engine service"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Train command
    train_parser = subparsers.add_parser("train", help="Trigger training job")
    train_parser.add_argument("--days", type=int, default=7, help="Days to look back")
    train_parser.add_argument("--ewc-lambda", type=float, default=500.0, help="EWC lambda value")
    train_parser.add_argument("--force", action="store_true", help="Force training")
    
    # JSONL train command
    train_jsonl_parser = subparsers.add_parser("train-jsonl", help="Trigger training from JSONL dataset")
    train_jsonl_parser.add_argument("--dataset", required=True, help="Path to JSONL dataset")
    train_jsonl_parser.add_argument("--learning-rate", type=float, default=None, help="Learning rate override")
    train_jsonl_parser.add_argument("--epochs", type=int, default=None, help="Epoch count override")
    train_jsonl_parser.add_argument("--batch-size", type=int, default=None, help="Batch size override")

    # Fisher command
    fisher_parser = subparsers.add_parser("fisher", help="Calculate Fisher matrix")
    fisher_parser.add_argument("--num-samples", type=int, default=1000, help="Number of samples")
    fisher_parser.add_argument("--adapter", help="Adapter version to use")
    
    # List adapters command
    subparsers.add_parser("list-adapters", help="List all adapters")
    
    # Adapter info command
    info_parser = subparsers.add_parser("adapter-info", help="Get adapter information")
    info_parser.add_argument("version", help="Adapter version")
    
    # Deploy command
    deploy_parser = subparsers.add_parser("deploy", help="Deploy an adapter")
    deploy_parser.add_argument("version", help="Adapter version to deploy")
    
    # Status command
    subparsers.add_parser("status", help="Get training status")
    
    # Metrics command
    subparsers.add_parser("metrics", help="Get training metrics")
    
    # Health command
    subparsers.add_parser("health", help="Check service health")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Execute command with base_url
    if args.command == "train":
        asyncio.run(train(args.days, args.ewc_lambda, args.force, args.base_url))
    elif args.command == "fisher":
        asyncio.run(calculate_fisher(args.num_samples, args.adapter, args.base_url))
    elif args.command == "train-jsonl":
        asyncio.run(train_jsonl(args.dataset, args.learning_rate, args.epochs, args.batch_size, args.base_url))
    elif args.command == "list-adapters":
        asyncio.run(list_adapters(args.base_url))
    elif args.command == "adapter-info":
        asyncio.run(get_adapter_info(args.version, args.base_url))
    elif args.command == "deploy":
        asyncio.run(deploy_adapter(args.version, args.base_url))
    elif args.command == "status":
        asyncio.run(get_status(args.base_url))
    elif args.command == "metrics":
        asyncio.run(get_metrics(args.base_url))
    elif args.command == "health":
        asyncio.run(health_check(args.base_url))


if __name__ == "__main__":
    main()
