#!/usr/bin/env python3
"""
Feedback Dashboard - Real-time Monitoring

Displays feedback statistics and model accuracy metrics in the terminal.

Usage:
    python feedback_dashboard.py [--interval SECONDS]
"""

import os
import sys
import time
import argparse
from datetime import datetime
from feedback_service import FeedbackService


def clear_screen():
    """Clear terminal screen."""
    os.system('cls' if os.name == 'nt' else 'clear')


def display_header():
    """Display dashboard header."""
    print("=" * 80)
    print(" " * 25 + "FEEDBACK COLLECTION DASHBOARD")
    print("=" * 80)
    print(f"Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


def display_overall_stats(service, days=7):
    """Display overall feedback statistics."""
    stats = service.get_feedback_stats(days=days)
    
    print(f"\n📊 Overall Statistics (Last {days} Days)")
    print("-" * 80)
    print(f"Total Feedback:      {stats['total_feedback']:>6} entries")
    print(f"Positive (👍):       {stats['positive_count']:>6} ({stats['positive_percentage']:>6.2f}%)")
    print(f"Negative (👎):       {stats['negative_count']:>6}")
    print(f"Unique Users:        {stats['unique_users']:>6}")
    print(f"Unique Sessions:     {stats['unique_sessions']:>6}")
    print(f"Avg Memory Used:     {stats['avg_memory_used']:>6} bytes")


def display_accuracy_by_model(service):
    """Display accuracy metrics by model."""
    metrics = service.get_model_accuracy()
    
    print(f"\n🎯 Model Accuracy Metrics")
    print("-" * 80)
    
    if not metrics:
        print("No accuracy data available yet.")
        return
    
    # Group by model
    models = {}
    for m in metrics:
        model_name = m['model']
        if model_name not in models:
            models[model_name] = []
        models[model_name].append(m)
    
    for model_name, model_metrics in models.items():
        print(f"\n{model_name}:")
        
        for m in model_metrics:
            intent = m['intent'] or 'all'
            project = m['project'] or 'all'
            
            # Create bar for visualization
            bar_length = int(m['accuracy_percentage'] / 2)  # Max 50 chars for 100%
            bar = "█" * bar_length
            
            print(f"  {intent:12} | {project:15} | "
                  f"{m['accuracy_percentage']:>6.2f}% {bar:50} | "
                  f"{m['positive_feedback']}👍/{m['negative_feedback']}👎 "
                  f"({m['total_feedback']} total)")


def display_accuracy_by_intent(service):
    """Display accuracy metrics by intent."""
    metrics = service.get_model_accuracy()
    
    print(f"\n🔍 Accuracy by Intent")
    print("-" * 80)
    
    if not metrics:
        print("No accuracy data available yet.")
        return
    
    # Group by intent
    intents = {}
    for m in metrics:
        intent = m['intent'] or 'unknown'
        if intent not in intents:
            intents[intent] = {
                'total': 0,
                'positive': 0,
                'negative': 0
            }
        intents[intent]['total'] += m['total_feedback']
        intents[intent]['positive'] += m['positive_feedback']
        intents[intent]['negative'] += m['negative_feedback']
    
    for intent, data in intents.items():
        accuracy = (data['positive'] / data['total'] * 100) if data['total'] > 0 else 0
        bar_length = int(accuracy / 2)
        bar = "█" * bar_length
        
        print(f"  {intent:15} | {accuracy:>6.2f}% {bar:50} | "
              f"{data['positive']}👍/{data['negative']}👎 ({data['total']} total)")


def display_recent_feedback(service, limit=5):
    """Display recent feedback entries."""
    # Get overall stats to find recent feedback
    # This is a simplified version - you may want to add a method to get recent entries
    print(f"\n📝 System Status")
    print("-" * 80)
    print("Real-time feedback collection active")
    print(f"Dashboard refresh interval: {args.interval}s")
    print("\nPress Ctrl+C to exit")


def run_dashboard(service, interval=5):
    """Run the dashboard with periodic updates."""
    try:
        while True:
            clear_screen()
            display_header()
            
            try:
                display_overall_stats(service, days=7)
                display_accuracy_by_model(service)
                display_accuracy_by_intent(service)
                display_recent_feedback(service)
            except Exception as e:
                print(f"\n⚠️  Error fetching data: {e}")
            
            print("\n" + "=" * 80)
            
            # Wait for next update
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\nDashboard stopped.")


def main():
    global args
    
    parser = argparse.ArgumentParser(
        description="Real-time feedback collection dashboard"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=5,
        help="Refresh interval in seconds (default: 5)"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=7,
        help="Days to look back for statistics (default: 7)"
    )
    parser.add_argument(
        "--db-host",
        default=os.getenv("POSTGRES_HOST", "localhost"),
        help="PostgreSQL host"
    )
    parser.add_argument(
        "--db-port",
        type=int,
        default=int(os.getenv("POSTGRES_PORT", "5432")),
        help="PostgreSQL port"
    )
    parser.add_argument(
        "--db-name",
        default=os.getenv("POSTGRES_DB", "ai_platform"),
        help="Database name"
    )
    parser.add_argument(
        "--db-user",
        default=os.getenv("POSTGRES_USER", "ai_user"),
        help="Database user"
    )
    parser.add_argument(
        "--db-password",
        default=os.getenv("POSTGRES_PASSWORD", "ai_password"),
        help="Database password"
    )
    
    args = parser.parse_args()
    
    try:
        # Initialize feedback service
        print("Connecting to database...")
        service = FeedbackService(
            db_host=args.db_host,
            db_port=args.db_port,
            db_name=args.db_name,
            db_user=args.db_user,
            db_password=args.db_password
        )
        print("✓ Connected to database\n")
        
        # Run dashboard
        run_dashboard(service, interval=args.interval)
        
        # Cleanup
        service.close()
        
    except Exception as e:
        print(f"✗ Dashboard error: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
