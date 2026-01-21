"""
Merlin Intelligence Integration

This module integrates Merlin with the AAS Shared Intelligence Service,
allowing Merlin to access all intelligence capabilities without duplicating
the intelligence stack.
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from loguru import logger

# Add AAS core to path for intelligence client
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.intelligence_client import MerlinIntelligenceClient, SimpleIntelligenceClient
except ImportError:
    logger.warning("AAS intelligence client not available - running in standalone mode")
    MerlinIntelligenceClient = None
    SimpleIntelligenceClient = None


class MerlinIntelligenceManager:
    """
    Merlin's interface to the AAS Shared Intelligence Service.
    
    This manager provides Merlin with access to all AAS intelligence capabilities
    including contextual awareness, optimization opportunities, and smart recommendations.
    """

    def __init__(self, aas_hub_url: str = "http://localhost:8000"):
        """Initialize Merlin's intelligence manager."""
        self.aas_hub_url = aas_hub_url
        self.client = None
        self.simple_client = None
        self.intelligence_cache = {}
        self.last_context_update = None
        
        if MerlinIntelligenceClient:
            self.client = MerlinIntelligenceClient(aas_hub_url)
            self.simple_client = SimpleIntelligenceClient("merlin", aas_hub_url)
            logger.info("🧙‍♂️ Merlin Intelligence Manager initialized with AAS integration")
        else:
            logger.warning("🧙‍♂️ Merlin Intelligence Manager running in standalone mode")

    async def get_system_awareness(self) -> Dict[str, Any]:
        """
        Get complete system awareness for Merlin.
        
        This provides Merlin with environmental context, system resources,
        cloud services, and optimization opportunities.
        """
        if not self.client:
            return {"error": "AAS intelligence not available"}
        
        try:
            async with self.client as client:
                context = await client.get_contextual_intelligence(include_opportunities=True)
                
                # Cache the context
                self.intelligence_cache["system_context"] = context
                self.last_context_update = asyncio.get_event_loop().time()
                
                # Extract key information for Merlin
                awareness = {
                    "system_health": context.get("health_score", 0.5),
                    "resources": {
                        "cpu_usage": self._extract_resource_usage(context, "CPU"),
                        "memory_usage": self._extract_resource_usage(context, "Memory"),
                        "disk_usage": self._extract_resource_usage(context, "Disk"),
                        "network_connected": context.get("network_status", {}).get("connected", False)
                    },
                    "cloud_services": self._extract_cloud_services(context),
                    "optimization_opportunities": context.get("optimization_opportunities", []),
                    "recommendations": context.get("recommendations", []),
                    "timestamp": context.get("timestamp")
                }
                
                logger.info(f"🧙‍♂️ System awareness updated: health={awareness['system_health']:.2f}")
                return awareness
                
        except Exception as e:
            logger.error(f"Failed to get system awareness: {e}")
            return {"error": str(e)}

    async def get_intelligent_recommendations(self, context: Optional[str] = None) -> List[str]:
        """
        Get intelligent recommendations for Merlin operations.
        
        Args:
            context: Optional context filter ("performance", "cost", "security")
        """
        if not self.client:
            return ["AAS intelligence not available - consider enabling integration"]
        
        try:
            async with self.client as client:
                recommendations = await client.get_smart_recommendations(context)
                
                # Add Merlin-specific intelligence
                merlin_recommendations = await self._get_merlin_specific_recommendations()
                recommendations.extend(merlin_recommendations)
                
                logger.info(f"🧙‍♂️ Got {len(recommendations)} intelligent recommendations")
                return recommendations
                
        except Exception as e:
            logger.error(f"Failed to get recommendations: {e}")
            return [f"Error getting recommendations: {e}"]

    async def optimize_llm_usage(self) -> Dict[str, Any]:
        """
        Get LLM usage optimization recommendations based on system context.
        """
        if not self.client:
            return {"error": "AAS intelligence not available"}
        
        try:
            async with self.client as client:
                # Get cost optimization recommendations
                cost_recommendations = await client.get_cost_optimization_recommendations()
                
                # Get model selection recommendations
                model_recommendations = await client.get_model_selection_recommendations()
                
                # Get system context for optimization
                context = await client.get_contextual_intelligence(include_opportunities=False)
                
                optimization = {
                    "cost_recommendations": cost_recommendations,
                    "model_recommendations": model_recommendations,
                    "system_load": {
                        "cpu": self._extract_resource_usage(context, "CPU"),
                        "memory": self._extract_resource_usage(context, "Memory")
                    },
                    "optimization_strategy": self._determine_optimization_strategy(context),
                    "estimated_savings": self._calculate_potential_savings(context)
                }
                
                logger.info(f"🧙‍♂️ LLM optimization analysis complete")
                return optimization
                
        except Exception as e:
            logger.error(f"Failed to optimize LLM usage: {e}")
            return {"error": str(e)}

    async def request_intelligent_task_processing(self, task_description: str, priority: str = "medium") -> Dict[str, Any]:
        """
        Request intelligent task processing through AAS.
        
        Args:
            task_description: Description of the task to process
            priority: Task priority level
        """
        if not self.client:
            return {"error": "AAS intelligence not available"}
        
        try:
            async with self.client as client:
                # Request intelligent task routing
                result = await client.request_intelligent_task_routing(
                    requesting_agent="Merlin",
                    task_id=None  # Let AAS find the best task
                )
                
                logger.info(f"🧙‍♂️ Intelligent task processing requested")
                return result
                
        except Exception as e:
            logger.error(f"Failed to request task processing: {e}")
            return {"error": str(e)}

    async def discover_collaboration_opportunities(self) -> List[Dict[str, Any]]:
        """
        Discover opportunities for Merlin to collaborate with other AAS components.
        """
        if not self.client:
            return []
        
        try:
            async with self.client as client:
                # Discover plugins that can help with various capabilities
                capabilities = ["code_analysis", "data_processing", "automation", "monitoring"]
                opportunities = []
                
                for capability in capabilities:
                    plugins = await client.discover_plugin_capabilities(capability)
                    if plugins:
                        opportunities.append({
                            "capability": capability,
                            "available_plugins": plugins,
                            "collaboration_potential": len(plugins)
                        })
                
                logger.info(f"🧙‍♂️ Found {len(opportunities)} collaboration opportunities")
                return opportunities
                
        except Exception as e:
            logger.error(f"Failed to discover collaboration opportunities: {e}")
            return []

    def get_quick_status(self) -> Dict[str, Any]:
        """
        Get quick status using synchronous client (for non-async contexts).
        """
        if not self.simple_client:
            return {"status": "intelligence_unavailable"}
        
        try:
            health = self.simple_client.health_check_sync()
            recommendations = self.simple_client.get_recommendations()
            
            return {
                "intelligence_service": health.get("service_status", "unknown"),
                "system_health": health.get("system_health", 0.5),
                "active_recommendations": len(recommendations),
                "top_recommendation": recommendations[0] if recommendations else None,
                "last_update": self.last_context_update
            }
            
        except Exception as e:
            logger.error(f"Failed to get quick status: {e}")
            return {"status": "error", "error": str(e)}

    def get_cost_insights(self) -> Dict[str, Any]:
        """
        Get cost optimization insights for Merlin (synchronous).
        """
        if not self.simple_client:
            return {"error": "Intelligence not available"}
        
        try:
            recommendations = self.simple_client.get_recommendations(context="cost")
            opportunities = self.simple_client.get_optimization_opportunities()
            
            # Filter for cost-related opportunities
            cost_opportunities = [
                opp for opp in opportunities 
                if opp.get("estimated_savings") and opp["estimated_savings"] > 0
            ]
            
            total_potential_savings = sum(
                opp.get("estimated_savings", 0) for opp in cost_opportunities
            )
            
            return {
                "cost_recommendations": recommendations,
                "cost_opportunities": cost_opportunities,
                "potential_savings": total_potential_savings,
                "optimization_count": len(cost_opportunities)
            }
            
        except Exception as e:
            logger.error(f"Failed to get cost insights: {e}")
            return {"error": str(e)}

    # Helper methods

    def _extract_resource_usage(self, context: Dict[str, Any], resource_name: str) -> float:
        """Extract resource usage from context data."""
        resources = context.get("system_resources", [])
        for resource in resources:
            if resource.get("name") == resource_name:
                return resource.get("current_usage", 0.0)
        return 0.0

    def _extract_cloud_services(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract cloud services information from context."""
        services = context.get("cloud_services", [])
        return [
            {
                "name": service.get("name"),
                "provider": service.get("provider"),
                "estimated_value": service.get("estimated_value", 0),
                "setup_required": service.get("setup_required", True)
            }
            for service in services
        ]

    async def _get_merlin_specific_recommendations(self) -> List[str]:
        """Get Merlin-specific recommendations based on current state."""
        recommendations = []
        
        # Check if cost optimization is available
        try:
            from merlin_cost_optimization import cost_optimization_manager
            current_spend = sum(
                sum(usage.total_cost for usage in usage_list)
                for usage_list in cost_optimization_manager.daily_usage.values()
            )
            
            if current_spend > cost_optimization_manager.budget_limit * 0.8:
                recommendations.append("🧙‍♂️ High LLM costs detected - consider using cost optimization features")
        except ImportError:
            pass
        
        # Check if predictive selection is available
        try:
            from merlin_predictive_selection import predictive_model_selector
            recommendations.append("🧙‍♂️ Enable predictive model selection for better performance")
        except ImportError:
            pass
        
        return recommendations

    def _determine_optimization_strategy(self, context: Dict[str, Any]) -> str:
        """Determine the best optimization strategy based on system context."""
        cpu_usage = self._extract_resource_usage(context, "CPU")
        memory_usage = self._extract_resource_usage(context, "Memory")
        
        if cpu_usage > 0.8 or memory_usage > 0.9:
            return "resource_constrained"
        elif cpu_usage < 0.3 and memory_usage < 0.5:
            return "performance_optimized"
        else:
            return "balanced"

    def _calculate_potential_savings(self, context: Dict[str, Any]) -> float:
        """Calculate potential cost savings from optimization opportunities."""
        opportunities = context.get("optimization_opportunities", [])
        return sum(
            opp.get("estimated_savings", 0) 
            for opp in opportunities 
            if opp.get("estimated_savings")
        )


# Global instance for easy access
_merlin_intelligence_manager = None


def get_merlin_intelligence_manager(aas_hub_url: str = "http://localhost:8000") -> MerlinIntelligenceManager:
    """Get or create the Merlin intelligence manager."""
    global _merlin_intelligence_manager
    
    if _merlin_intelligence_manager is None:
        _merlin_intelligence_manager = MerlinIntelligenceManager(aas_hub_url)
    
    return _merlin_intelligence_manager


# Convenience functions for Merlin scripts
def get_system_status() -> Dict[str, Any]:
    """Get quick system status (synchronous)."""
    manager = get_merlin_intelligence_manager()
    return manager.get_quick_status()


def get_smart_recommendations(context: Optional[str] = None) -> List[str]:
    """Get smart recommendations (synchronous)."""
    manager = get_merlin_intelligence_manager()
    if manager.simple_client:
        return manager.simple_client.get_recommendations(context)
    return []


def get_cost_optimization_insights() -> Dict[str, Any]:
    """Get cost optimization insights (synchronous)."""
    manager = get_merlin_intelligence_manager()
    return manager.get_cost_insights()


async def main():
    """Demo of Merlin intelligence integration."""
    print("🧙‍♂️ Merlin Intelligence Integration Demo")
    print("=" * 50)
    
    manager = get_merlin_intelligence_manager()
    
    # Get system awareness
    print("\n📊 Getting system awareness...")
    awareness = await manager.get_system_awareness()
    
    if "error" not in awareness:
        print(f"System Health: {awareness['system_health']:.2f}")
        print(f"CPU Usage: {awareness['resources']['cpu_usage']*100:.1f}%")
        print(f"Memory Usage: {awareness['resources']['memory_usage']*100:.1f}%")
        print(f"Cloud Services: {len(awareness['cloud_services'])}")
        print(f"Optimization Opportunities: {len(awareness['optimization_opportunities'])}")
    else:
        print(f"Error: {awareness['error']}")
    
    # Get recommendations
    print("\n💡 Getting intelligent recommendations...")
    recommendations = await manager.get_intelligent_recommendations()
    for i, rec in enumerate(recommendations[:5], 1):
        print(f"  {i}. {rec}")
    
    # Get LLM optimization
    print("\n🔮 Getting LLM optimization recommendations...")
    optimization = await manager.optimize_llm_usage()
    
    if "error" not in optimization:
        print(f"Optimization Strategy: {optimization.get('optimization_strategy', 'unknown')}")
        print(f"Potential Savings: ${optimization.get('estimated_savings', 0):.2f}")
    else:
        print(f"Error: {optimization['error']}")
    
    # Discover collaboration opportunities
    print("\n🤝 Discovering collaboration opportunities...")
    opportunities = await manager.discover_collaboration_opportunities()
    for opp in opportunities:
        print(f"  {opp['capability']}: {opp['collaboration_potential']} plugins available")
    
    print("\n✨ Merlin is now magically intelligent! ✨")


if __name__ == "__main__":
    asyncio.run(main())